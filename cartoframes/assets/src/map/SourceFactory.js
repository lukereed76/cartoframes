export default function SourceFactory() {
  const sourceTypes = { GeoJSON, Query, MVT, BQMVT };

  this.createSource = (layer) => {
    return sourceTypes[layer.type](layer);
  };
}

function GeoJSON(layer) {
  const options = JSON.parse(JSON.stringify(layer.options));
  const data = _decodeJSONData(layer.data);

  return new carto.source.GeoJSON(data, options);
}

function Query(layer) {
  const auth = {
    username: layer.credentials.username,
    apiKey: layer.credentials.api_key || 'default_public'
  };

  const config = {
    serverURL: layer.credentials.base_url || `https://${layer.credentials.username}.carto.com/`
  };

  return new carto.source.SQL(layer.data, auth, config);
}

function MVT(layer) {
  return new carto.source.MVT(layer.data.file, JSON.parse(layer.data.metadata));
}

function BQMVT(layer) {
  const data = layer.data.data;
  const metadata = layer.data.metadata;
  return new carto.source.BQMVT({
    projectId: data.project_id,
    datasetId: data.dataset_id,
    tableId: data.table_id,
    token: data.token
  }, metadata, {
    viewportZoomToSourceZoom: (zoom) => {
      if (zoom > 13) {
        return 14;
      }
      return zoom;
    }
  });
}

function _decodeJSONData(b64Data) {
  return JSON.parse(pako.inflate(atob(b64Data), { to: 'string' }));
}