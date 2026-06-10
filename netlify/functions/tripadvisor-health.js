const { RAPIDAPI_HOST, json } = require('./_shared');

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') return json(204, {});
  return json(200, {
    ok: true,
    rapidapi_key_configured: Boolean(process.env.RAPIDAPI_KEY),
    provider_host: RAPIDAPI_HOST,
  });
};
