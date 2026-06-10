const { json } = require('./_shared');
const { tripadvisorReviews } = require('./tripadvisor');

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') return json(204, {});
  const query = event.queryStringParameters || {};
  const city = (query.city || '').trim();
  const contentId = (query.contentId || query.content_id || '').trim();
  if (!city && !contentId) return json(400, { ok: false, error: 'city or contentId is required' });
  const limit = Math.max(1, Math.min(Number(query.limit || 8), 20));
  try {
    return json(200, await tripadvisorReviews(city, query.name || '', query.category || 'attractions', contentId, limit));
  } catch (error) {
    return json(502, { ok: false, error: error.message });
  }
};
