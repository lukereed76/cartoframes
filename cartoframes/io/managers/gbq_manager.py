import os
import math

from google.cloud import bigquery
from google.oauth2.credentials import Credentials

from ...utils.logger import log
from ...utils.utils import dtypes2vl, create_hash

MVT_DATASET = 'mvt_pool'
PROJECT_KEY = 'GOOGLE_CLOUD_PROJECT'


class GBQManager:

    DATA_SIZE_LIMIT = 10 * 1024 * 1024  # 10 MB

    def __init__(self, project=None, token=None, credentials=None):
        credentials = Credentials(token) if token else credentials

        self.token = token
        self.project = project if project else os.environ[PROJECT_KEY]
        self.client = bigquery.Client(project=project, credentials=credentials)

    def download_dataframe(self, query):
        query_job = self.client.query(query)
        return query_job.to_dataframe()

    def build_mvt_data(self, query):
        return {
            'projectId': self.project,
            'datasetId': MVT_DATASET,
            'tableId': create_hash(query),
            'token': self.token
        }

    def fetch_mvt_info(self, query, index_col, geom_col):
        metadata = self.fetch_mvt_metadata(query, index_col, geom_col)
        bounds, zoom = self.fetch_bounds(query)
        return {
            'metadata': metadata,
            'bounds': bounds,
            'zoom': zoom
        }

    def fetch_mvt_metadata(self, query, index_col='geoid', geom_col='geom'):
        metadata_query = '''
            WITH q as ({})
            SELECT * FROM q LIMIT 1
        '''.format(query)

        result = self.client.query(metadata_query).to_dataframe()

        if index_col not in result.columns:
            raise ValueError('No "{}" column found.'.format(index_col))

        properties = {}
        for column in result.columns:
            if column == geom_col:
                continue
            dtype = result.dtypes[column]
            properties[column] = {'type': dtypes2vl(dtype)}

        return {
            'idProperty': index_col,
            'properties': properties
        }

    def fetch_bounds(self, query):
        # TODO: optimize query
        bounds_query = '''
            WITH data AS (
                {0}
            ),
            data_bounds AS (
                SELECT jarroyo_tests.ST_EnvelopeBox(TO_HEX(ST_ASBINARY(geom))) AS bbox
                FROM data
            )
            SELECT
                MIN(bbox.xmin) as xmin,
                MAX(bbox.xmax) as xmax,
                MIN(bbox.ymin) as ymin,
                MAX(bbox.ymax) as ymax
            FROM data_bounds
        '''.format(query)
        job = self.client.query(bounds_query)
        result = job.to_dataframe()
        bounds = result.iloc[0]
        zoom = math.floor(math.log2(360 / (bounds.xmax - bounds.xmin)))
        return [[bounds.xmin, bounds.ymin], [bounds.xmax, bounds.ymax]], zoom

    def trigger_mvt_generation(self, query, zoom, index_col='geoid', geom_col='geom'):
        table_name = create_hash(query)

        if self.check_table_exists(table_name):
            log.info('DEBUG: table cached')
            return

        xo = 360./(2**zoom)
        yo = 180./(2**zoom)

        # TODO: optimize query
        generation_query = '''
        CREATE TABLE {dataset}.{table} AS (
            WITH data AS (
                {query}
            ),
            data_bounds AS (
                SELECT geoid, jarroyo_tests.ST_EnvelopeBox(TO_HEX(ST_ASBINARY(geom))) AS bbox
                FROM data
            ),
            global_bounds AS (
                SELECT
                    MIN(bbox.xmin) as gxmin,
                    MAX(bbox.xmax) as gxmax,
                    MIN(bbox.ymin) as gymin,
                    MAX(bbox.ymax) as gymax
                FROM data_bounds
            ),
            global_bbox AS (
                SELECT tiler.getTilesBBOX(gxmin-{xo}, gymin-{yo}, gxmax+{xo}, gymax+{yo}, {zoom}, 16/4096) AS gbbox
                FROM global_bounds
            ),
            tiles_bbox AS (
                SELECT z, x, y, xmin, ymin, xmax, ymax
                FROM global_bbox
                CROSS JOIN UNNEST(global_bbox.gbbox)
            ),
            tiles_xyz AS (
                SELECT b.z, b.x, b.y, a.geoid
                FROM data_bounds a, tiles_bbox b
                WHERE NOT ((bbox.xmin > b.xmax) OR
                           (bbox.xmax < b.xmin) OR
                           (bbox.ymin > b.ymax) OR
                           (bbox.ymax < b.ymin))
            ),
            tiles_geom AS (
                SELECT b.z, b.x, b.y, a.geoid, ST_ASGEOJSON(a.geom) AS geom, a.* EXCEPT (geoid, geom)
                FROM data a, tiles_xyz b
                WHERE a.geoid = b.geoid
            ),
            tiles_mvt AS (
                SELECT tiler.ST_ASMVT(b.z, b.x, b.y, ARRAY_AGG(TO_JSON_STRING(a)), 0) AS tile
                FROM tiles_geom a, tiles_xyz b
                WHERE a.geoid = b.geoid AND a.x = b.x AND a.y = b.y AND a.z = b.z
                GROUP BY b.z, b.x, b.y
            )
            SELECT z, x, y, mvt
            FROM tiles_mvt
            CROSS JOIN UNNEST(tiles_mvt.tile)
        )
        '''.format(dataset=MVT_DATASET, table=table_name, query=query,
                   xo=xo, yo=yo, zoom=zoom)
        job = self.client.query(generation_query)
        job.result()  # Wait for the job to complete.

    def estimated_data_size(self, query):
        log.info('Estimating size. This may take a few seconds')
        estimation_query = '''
            WITH q as ({})
            SELECT SUM(CHAR_LENGTH(ST_ASTEXT(geom))) AS s FROM q
        '''.format(query)
        estimation_query_job = self.client.query(estimation_query)
        result = estimation_query_job.to_dataframe()
        estimated_size = result.s[0] * 0.425
        if estimated_size < self.DATA_SIZE_LIMIT:
            log.info('DEBUG: small dataset ({:.2f} KB)'.format(estimated_size / 1024))
        else:
            log.info('DEBUG: big dataset ({:.2f} MB)'.format(estimated_size / 1024 / 1024))
        return estimated_size

    def check_table_exists(self, table_name):
        check_query = '''
            SELECT size_bytes FROM `{0}`.__TABLES__ WHERE table_id='{1}'
        '''.format(MVT_DATASET, table_name)
        check_job = self.client.query(check_query)
        result = check_job.to_dataframe()
        return not result.empty

    def get_total_bytes_processed(self, query):
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        query_job = self.client.query(query, job_config=job_config)
        return query_job.total_bytes_processed
