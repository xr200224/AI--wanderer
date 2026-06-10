const {
  RAPIDAPI_HOST,
  categoryToPath,
  endpointFor,
  futureDates,
  getGeoId,
  json,
  normalizeItem,
  normalizeMedia,
  normalizeReviews,
  pickCategoryRecords,
  rankRecordsForQuery,
  rapidapiGet,
} = require('./_shared');

async function tripadvisorSearch(city, keyword, category, limit) {
  const kind = categoryToPath(category);
  const geoId = getGeoId(city);
  if (!geoId) throw new Error(`暂未配置 ${city} 的 TripAdvisor geoId`);

  const [start, end] = futureDates();
  const params = { geoId };
  if (keyword) params.query = keyword;
  if (kind === 'hotels') Object.assign(params, { checkIn: start, checkOut: end });
  if (kind === 'attractions') Object.assign(params, { startDate: start, endDate: end });

  const payload = await rapidapiGet(endpointFor(kind, 'search'), params);
  const records = rankRecordsForQuery(
    pickCategoryRecords(payload, kind, Math.max(limit * 6, 30)),
    keyword
  ).slice(0, limit);

  return {
    ok: true,
    source: 'rapidapi-tripadvisor-com1-netlify',
    provider_host: RAPIDAPI_HOST,
    category: kind,
    query: [city, keyword].filter(Boolean).join(' '),
    geo_id: geoId,
    items: records.map((item, index) => normalizeItem(item, city, index)),
    fetched_at: Math.floor(Date.now() / 1000),
  };
}

async function findTripadvisorContent(city, name, category = 'attractions') {
  const data = await tripadvisorSearch(city, name, category, 1);
  const matched = data.items && data.items[0];
  if (!matched) throw new Error(`TripAdvisor 未找到 ${city} ${name}`);
  return matched;
}

async function tripadvisorReviews(city, name, category, contentId, limit) {
  let kind = categoryToPath(category);
  let matched = {};
  let id = contentId;
  if (!id) {
    matched = await findTripadvisorContent(city, name, kind);
    id = matched.content_id || matched.id || '';
    if (matched.content_type) kind = categoryToPath(matched.content_type);
  }
  if (!id) throw new Error('Missing TripAdvisor contentId');

  const reviewPayload = await rapidapiGet(endpointFor(kind, 'reviews'), { contentId: id });
  const { reviews, summary } = normalizeReviews(reviewPayload, limit);
  let media = [];
  try {
    media = normalizeMedia(await rapidapiGet(endpointFor(kind, 'media'), { contentId: id }), 12);
  } catch {
    media = [];
  }
  return {
    ok: true,
    source: 'rapidapi-tripadvisor-com1-netlify',
    provider_host: RAPIDAPI_HOST,
    category: kind,
    city,
    query_name: name,
    content_id: id,
    matched,
    summary,
    reviews,
    media,
    fetched_at: Math.floor(Date.now() / 1000),
  };
}

async function tripadvisorDestination(city, limit) {
  const errors = {};
  async function safeItems(label, keyword, category, itemLimit) {
    try {
      return (await tripadvisorSearch(city, keyword, category, itemLimit)).items || [];
    } catch (error) {
      errors[label] = error.message;
      return [];
    }
  }

  const attractions = await safeItems('attractions', '景点', 'attractions', limit);
  const restaurants = await safeItems('restaurants', '美食', 'restaurants', Math.min(limit, 4));
  const hotels = await safeItems('hotels', '酒店', 'hotels', Math.min(limit, 4));
  const guide_cards = [];
  for (const [group, label] of [[attractions, '热门景点'], [restaurants, '美食口碑'], [hotels, '住宿推荐']]) {
    for (const item of group.slice(0, 3)) {
      guide_cards.push({
        type: label,
        name: item.name,
        rating: item.rating,
        review_count: item.review_count,
        image_url: item.image_url,
        content_id: item.content_id,
        content_type: item.content_type,
        summary: item.category || item.ranking || item.address,
      });
    }
  }
  return {
    ok: true,
    source: 'rapidapi-tripadvisor-com1-netlify',
    provider_host: RAPIDAPI_HOST,
    city,
    geo_id: getGeoId(city),
    attractions,
    restaurants,
    hotels,
    guide_cards,
    errors,
    fetched_at: Math.floor(Date.now() / 1000),
  };
}

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') return json(204, {});
  const query = event.queryStringParameters || {};
  const endpoint = query.endpoint || '';

  try {
    if (endpoint === 'health') {
      return json(200, {
        ok: true,
        rapidapi_key_configured: Boolean(process.env.RAPIDAPI_KEY),
        provider_host: RAPIDAPI_HOST,
      });
    }

    if (endpoint === 'search') {
      const city = (query.city || '').trim();
      if (!city) return json(400, { ok: false, error: 'city is required' });
      const limit = Math.max(1, Math.min(Number(query.limit || 6), 20));
      return json(200, await tripadvisorSearch(city, query.keyword || '景点', query.category || 'attractions', limit));
    }

    if (endpoint === 'reviews') {
      const limit = Math.max(1, Math.min(Number(query.limit || 8), 20));
      const city = (query.city || '').trim();
      const contentId = (query.contentId || query.content_id || '').trim();
      if (!city && !contentId) return json(400, { ok: false, error: 'city or contentId is required' });
      return json(200, await tripadvisorReviews(city, query.name || '', query.category || 'attractions', contentId, limit));
    }

    if (endpoint === 'hotels') {
      const city = (query.city || '').trim();
      if (!city) return json(400, { ok: false, error: 'city is required' });
      const limit = Math.max(1, Math.min(Number(query.limit || 3), 10));
      return json(200, await tripadvisorSearch(city, '酒店', 'hotels', limit));
    }

    if (endpoint === 'destination') {
      const city = (query.city || '').trim();
      if (!city) return json(400, { ok: false, error: 'city is required' });
      const limit = Math.max(1, Math.min(Number(query.limit || 6), 10));
      return json(200, await tripadvisorDestination(city, limit));
    }

    return json(404, { ok: false, error: `unknown tripadvisor endpoint: ${endpoint}` });
  } catch (error) {
    return json(502, {
      ok: false,
      error: error.message,
      trace: error.stack ? error.stack.split('\n').slice(0, 4).join('\n') : '',
    });
  }
};

module.exports.tripadvisorSearch = tripadvisorSearch;
module.exports.tripadvisorReviews = tripadvisorReviews;
module.exports.tripadvisorDestination = tripadvisorDestination;
