const { json } = require('./_shared');
const { tripadvisorDestination } = require('./tripadvisor');

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') return json(204, {});
  const query = event.queryStringParameters || {};
  const city = (query.city || '').trim();
  if (!city) return json(400, { ok: false, error: 'city is required' });
  const limit = Math.max(1, Math.min(Number(query.limit || 6), 10));
  try {
    return json(200, await tripadvisorDestination(city, limit));
  } catch (error) {
    return json(502, { ok: false, error: error.message });
  }
};
