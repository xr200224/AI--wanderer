const RAPIDAPI_HOST = process.env.RAPIDAPI_TRIPADVISOR_HOST || 'tripadvisor-com1.p.rapidapi.com';
const RAPIDAPI_TIMEOUT = Number(process.env.RAPIDAPI_TIMEOUT || 12) * 1000;

const CITY_GEO_IDS = {
  '北京': '294212',
  '上海': '308272',
  '广州': '298555',
  '深圳': '297415',
  '成都': '297463',
  '重庆': '294213',
  '西安': '298557',
  '杭州': '298559',
  '南京': '294220',
  '苏州': '297442',
  '武汉': '297437',
  '长沙': '494932',
  '厦门': '297407',
  '青岛': '297458',
  '昆明': '298558',
  '大理': '303781',
  '丽江': '303783',
  '桂林': '298556',
  '三亚': '297427',
  '安康': '1152549',
  'New York': '60763',
  '纽约': '60763',
};

const PLACE_QUERY_ALIASES = {
  '洪崖洞': ['hongya', 'hongyadong'],
  '磁器口': ['ciqikou', 'porcelain port'],
  '磁器口古镇': ['ciqikou', 'porcelain port'],
  '解放碑': ['jiefangbei', 'liberation monument'],
  '解放碑步行街': ['jiefangbei', 'liberation monument'],
  '黄桷坪': ['huangjueping', 'graffiti street'],
  '黄桷坪涂鸦街': ['huangjueping', 'graffiti street'],
  '鹅岭二厂': ['eling', 'second factory', 'testbed 2'],
  '鹅岭二厂文创公园': ['eling', 'second factory', 'testbed 2'],
  '武隆': ['wulong', 'karst'],
  '武隆天坑': ['wulong', 'karst'],
  '兵马俑': ['terra-cotta', 'terracotta', 'warriors'],
};

function json(statusCode, body) {
  return {
    statusCode,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    },
    body: JSON.stringify(body),
  };
}

function categoryToPath(category = '') {
  if (['hotel', 'hotels'].includes(category)) return 'hotels';
  if (['restaurant', 'restaurants', 'food'].includes(category)) return 'restaurants';
  return 'attractions';
}

function endpointFor(kind, endpoint) {
  const map = {
    search: {
      hotels: '/hotels/search',
      restaurants: '/restaurants/search',
      attractions: '/attractions/search',
    },
    reviews: {
      hotels: '/hotels/reviews',
      restaurants: '/restaurants/reviews',
      attractions: '/attractions/reviews',
    },
    media: {
      hotels: '/hotels/media-gallery',
      restaurants: '/restaurants/media-gallery',
      attractions: '/attractions/media-gallery',
    },
  };
  return (map[endpoint] && map[endpoint][kind]) || map[endpoint].attractions;
}

function getGeoId(city = '') {
  const trimmed = String(city).trim();
  return CITY_GEO_IDS[trimmed] || CITY_GEO_IDS[trimmed.replace(/[市省区县]$/g, '')] || '';
}

function futureDates() {
  const start = new Date(Date.now() + 30 * 86400000);
  const end = new Date(start.getTime() + 86400000);
  return [start.toISOString().slice(0, 10), end.toISOString().slice(0, 10)];
}

async function rapidapiGet(path, params = {}) {
  if (!process.env.RAPIDAPI_KEY) {
    throw new Error('Missing RAPIDAPI_KEY environment variable');
  }
  const url = new URL(`https://${RAPIDAPI_HOST}${path}`);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value));
  });
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), RAPIDAPI_TIMEOUT);
  try {
    const res = await fetch(url, {
      signal: ctrl.signal,
      headers: {
        'x-rapidapi-key': process.env.RAPIDAPI_KEY,
        'x-rapidapi-host': RAPIDAPI_HOST,
        'accept': 'application/json',
      },
    });
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { raw: text };
    }
    if (!res.ok) throw new Error(`RapidAPI ${res.status}: ${text.slice(0, 240)}`);
    return data;
  } finally {
    clearTimeout(timer);
  }
}

function deepValues(value, out = []) {
  if (!value || out.length > 5000) return out;
  if (Array.isArray(value)) {
    value.forEach(item => deepValues(item, out));
  } else if (typeof value === 'object') {
    out.push(value);
    Object.values(value).forEach(item => deepValues(item, out));
  }
  return out;
}

function unwrapText(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return cleanHtml(value);
  if (typeof value === 'number') return String(value);
  if (typeof value === 'object') {
    for (const key of ['text', 'string', 'localizedString', 'value', 'label', 'title']) {
      if (value[key]) return unwrapText(value[key]);
    }
  }
  return '';
}

function firstValue(obj, keys, fallback = '') {
  if (!obj || typeof obj !== 'object') return fallback;
  for (const key of keys) {
    if (obj[key] !== undefined && obj[key] !== null && obj[key] !== '') return obj[key];
  }
  for (const node of deepValues(obj)) {
    if (node === obj) continue;
    for (const key of keys) {
      if (node[key] !== undefined && node[key] !== null && node[key] !== '') return node[key];
    }
  }
  return fallback;
}

function cleanHtml(value = '') {
  return String(value)
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

function extractImages(value, limit = 6) {
  const images = [];
  const urlRe = /^https?:\/\/.+\.(jpg|jpeg|png|webp)(\?.*)?$/i;
  for (const node of deepValues(value)) {
    for (const key of ['url', 'photoUrl', 'imageUrl', 'thumbnailUrl', 'largeUrl', 'mediumUrl', 'smallUrl']) {
      const candidate = unwrapText(node[key]);
      if (candidate && (urlRe.test(candidate) || candidate.includes('media'))) {
        if (!images.includes(candidate)) images.push(candidate);
      }
      if (images.length >= limit) return images;
    }
  }
  return images;
}

function extractContentId(item) {
  const cardLink = item && item.cardLink;
  if (cardLink && typeof cardLink === 'object') {
    const params = cardLink.params || {};
    if (params.contentId || params.detailId) return unwrapText(params.contentId || params.detailId);
    const routeUrl = unwrapText(cardLink.url || cardLink.nonCanonicalUrl);
    const match = routeUrl.match(/(?:contentId=|[-_]?d)(\d{4,})/);
    if (match) return match[1];
  }
  return unwrapText(firstValue(item, ['locationId', 'location_id', 'geoId', 'id', 'place_id'], ''));
}

function extractContentType(item, fallback = '') {
  const cardLink = item && item.cardLink;
  if (cardLink && typeof cardLink === 'object' && cardLink.params && cardLink.params.contentType) {
    return unwrapText(cardLink.params.contentType);
  }
  const saveId = item && item.saveId;
  if (saveId && typeof saveId === 'object' && saveId.type && saveId.type !== 'location') {
    return unwrapText(saveId.type);
  }
  return fallback;
}

function normalizeItem(item, city, index) {
  const name = unwrapText(firstValue(item, ['name', 'title', 'localizedName', 'label', 'cardTitle'], '')) || `${city}热门地点 ${index + 1}`;
  const images = extractImages(item, 6);
  const contentId = extractContentId(item);
  return {
    id: String(contentId || `tripadvisor_${index + 1}`),
    content_id: String(contentId || ''),
    content_type: String(extractContentType(item, '') || ''),
    name,
    rating: unwrapText(firstValue(item, ['rating', 'bubbleRating', 'reviewRating', 'localizedRating'], '')),
    review_count: unwrapText(firstValue(item, ['numReviews', 'num_reviews', 'reviewCount', 'reviewsCount', 'numberReviews'], '')),
    address: unwrapText(firstValue(item, ['address', 'addressString', 'locationString', 'location_string', 'primaryInfo', 'secondaryInfo'], '')) || `${city} · ${name}`,
    ranking: unwrapText(firstValue(item, ['rankingString', 'ranking', 'rankingText', 'trackingTitle'], '')),
    category: unwrapText(firstValue(item, ['category', 'subcategory', 'type', 'primaryInfo'], '')),
    url: unwrapText(firstValue(item, ['webUrl', 'website', 'url', 'externalUrl', 'link'], '')),
    image_url: images[0] || '',
    images,
    price: cleanHtml(firstValue(item, ['priceForDisplay', 'merchandisingText', 'priceWithPrefix'], '')),
    latitude: unwrapText(firstValue(item, ['latitude', 'lat'], '')),
    longitude: unwrapText(firstValue(item, ['longitude', 'lng', 'lon'], '')),
    raw: item,
  };
}

function pickCategoryRecords(payload, kind, limit) {
  const data = payload && payload.data;
  if (data && Array.isArray(data[kind])) return data[kind].filter(Boolean).slice(0, limit);
  const records = [];
  for (const node of deepValues(payload)) {
    const name = unwrapText(firstValue(node, ['name', 'title', 'localizedName', 'label', 'cardTitle'], ''));
    const id = unwrapText(firstValue(node, ['locationId', 'location_id', 'geoId', 'id', 'saveId', 'trackingTitle'], ''));
    if (name && id) records.push(node);
    if (records.length >= limit) break;
  }
  return records;
}

function queryAliases(query = '') {
  const aliases = [String(query).trim().toLowerCase()].filter(Boolean);
  for (const [key, values] of Object.entries(PLACE_QUERY_ALIASES)) {
    if (String(query).includes(key)) aliases.push(...values);
  }
  return [...new Set(aliases.filter(Boolean))];
}

function recordText(item) {
  return [
    firstValue(item, ['name', 'title', 'localizedName', 'label', 'cardTitle'], ''),
    firstValue(item, ['rankingString', 'ranking', 'category', 'subcategory', 'address', 'locationString'], ''),
    firstValue(item, ['trackingTitle', 'primaryInfo', 'secondaryInfo'], ''),
  ].map(unwrapText).join(' ').toLowerCase();
}

function rankRecordsForQuery(records, query) {
  const aliases = queryAliases(query);
  if (!aliases.length) return records;
  return records
    .map((item, index) => {
      const text = recordText(item);
      const score = aliases.reduce((sum, value) => sum + (value && text.includes(value.toLowerCase()) ? 10 : 0), 0);
      return { item, score, index };
    })
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map(row => row.item);
}

function normalizeReview(item, index) {
  const userProfile = item && typeof item.userProfile === 'object' ? item.userProfile : {};
  const photos = extractImages(item.photos || item, 6);
  return {
    id: unwrapText(firstValue(item, ['objectId', 'stableDiffingType', 'trackingTitle'], '')) || `review_${index + 1}`,
    title: cleanHtml(item.htmlTitle || item.title || ''),
    text: cleanHtml(item.htmlText || item.text || item.body || ''),
    user: cleanHtml(firstValue(userProfile, ['displayName', 'username', 'name'], '')) || `TripAdvisor 用户 ${index + 1}`,
    rating: unwrapText(firstValue(item, ['rating', 'bubbleRating', 'localizedRating'], '')),
    date: cleanHtml(item.publishedDate || item.dateVisitedValue || ''),
    visit_type: cleanHtml(item.tripTypeText || item.tripTypeValue || ''),
    helpful: cleanHtml(firstValue(item, ['helpfulVotes', 'helpfulVoteText'], '')),
    photos,
    has_photos: photos.length > 0,
  };
}

function normalizeReviews(payload, limit) {
  const reviews = [];
  let summary = {};
  for (const node of deepValues(payload)) {
    const typename = unwrapText(node.__typename);
    if (typename === 'AppPresentation_TravelerInsights') {
      summary = {
        rating: unwrapText(node.localizedRating || node.rating),
        count: unwrapText(node.count),
        rating_text: cleanHtml(node.ratingText || ''),
      };
    }
    if (typename === 'AppPresentation_UserReviewSection') {
      const review = normalizeReview(node, reviews.length);
      if (review.text || review.title) reviews.push(review);
    }
  }
  reviews.sort((a, b) => Number(a.has_photos === false) - Number(b.has_photos === false) || Number(b.rating || 0) - Number(a.rating || 0));
  return { reviews: reviews.slice(0, limit), summary };
}

function normalizeMedia(payload, limit = 12) {
  return extractImages(payload, limit).map(url => ({ url, caption: '' }));
}

module.exports = {
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
};
