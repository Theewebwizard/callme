/**
 * CallMe REST API Client
 * Connects React frontend directly to FastAPI backend.
 */

const API_BASE = '/api';

function getTokenExpiration(token) {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const base64Url = parts[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    const payload = JSON.parse(jsonPayload);
    return payload.exp ? payload.exp * 1000 : null; // Expiration in milliseconds
  } catch {
    return null;
  }
}

let isRefreshingToken = false;
let refreshPromise = null;

async function tryRefreshToken() {
  if (isRefreshingToken && refreshPromise) return refreshPromise;
  isRefreshingToken = true;
  refreshPromise = (async () => {
    try {
      const currentToken = localStorage.getItem('callme_token');
      if (!currentToken || currentToken === 'undefined' || currentToken === 'null') return;
      const res = await fetch(`${API_BASE}/businesses/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentToken.trim()}`,
        },
      });
      if (res.ok) {
        const data = await res.json();
        if (data && data.access_token) {
          localStorage.setItem('callme_token', data.access_token);
          return data.access_token;
        }
      }
    } catch (err) {
      console.warn('Automated token refresh failed:', err);
    } finally {
      isRefreshingToken = false;
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

async function request(path, options = {}) {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  let token = localStorage.getItem('callme_token');
  const adminKey = localStorage.getItem('callme_admin_key') || 'admin';
  const role = localStorage.getItem('callme_role');
  const isAdminPath = path.startsWith('/admin') || role === 'admin';

  if (isAdminPath) {
    headers['Authorization'] = `Bearer ${adminKey.trim()}`;
    headers['X-Admin-API-Key'] = adminKey.trim();
  } else {
    // Automated Token Refresh Interceptor: If within 5 minutes (300,000 ms) of expiration, refresh token proactively
    if (token && token.trim() && token !== 'undefined' && token !== 'null' && !path.includes('/refresh')) {
      const expMs = getTokenExpiration(token);
      if (expMs) {
        const timeRemaining = expMs - Date.now();
        // Proactively refresh when less than 5 minutes remain and token hasn't already expired
        if (timeRemaining > 0 && timeRemaining < 300000) {
          await tryRefreshToken();
          token = localStorage.getItem('callme_token');
        }
      }
    }

    if (token && token.trim() && token !== 'undefined' && token !== 'null' && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token.trim()}`;
    }
  }

  try {
    const res = await fetch(url, {
      ...options,
      headers: options.body instanceof FormData ? { ...options.headers, ...(headers['Authorization'] ? { Authorization: headers['Authorization'] } : {}) } : headers,
    });

    if (!res.ok) {
      if (res.status === 401 && !options._retry && !path.includes('/refresh')) {
        const refreshedToken = await tryRefreshToken();
        if (refreshedToken) {
          const retryHeaders = {
            ...headers,
            'Authorization': `Bearer ${refreshedToken.trim()}`,
          };
          const retryRes = await fetch(url, {
            ...options,
            _retry: true,
            headers: options.body instanceof FormData ? { ...options.headers, Authorization: retryHeaders['Authorization'] } : retryHeaders,
          });
          if (retryRes.ok) {
            const ct = retryRes.headers.get('content-type') || '';
            if (ct.includes('application/json')) return await retryRes.json();
            return await retryRes.text();
          }
        }
        localStorage.removeItem('callme_token');
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('callme:unauthorized', { detail: { path } }));
        }
      } else if (res.status === 401) {
        localStorage.removeItem('callme_token');
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('callme:unauthorized', { detail: { path } }));
        }
      }
      let detail = `Error ${res.status}`;
      try {
        const errJson = await res.json();
        detail = errJson.detail || detail;
      } catch {
        detail = await res.text();
      }
      throw new Error(detail || `HTTP Error ${res.status}`);
    }

    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return await res.json();
    }
    return await res.text();
  } catch (err) {
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error('Cannot connect to backend server at http://localhost:8000. Ensure FastAPI is running.');
    }
    throw err;
  }
}

export const api = {
  // System Health
  getHealth: () => fetch(`${API_BASE}/health`).then((r) => r.json()).catch(() => ({ status: 'offline' })),

  // Businesses (Tenants)
  listBusinesses: () => request('/businesses'),
  getBusiness: (id) => request(`/businesses/${id}`),
  loginBusiness: async (email, password) => {
    const res = await request('/businesses/login', { method: 'POST', body: JSON.stringify({ email, password }) });
    if (res && res.access_token) {
      localStorage.setItem('callme_token', res.access_token);
    }
    return res;
  },
  accessBusiness: async (identifier) => {
    const res = await request('/businesses/access', { method: 'POST', body: JSON.stringify({ identifier }) });
    if (res && res.access_token) {
      localStorage.setItem('callme_token', res.access_token);
    }
    return res;
  },
  googleAuth: async (payload) => {
    const res = await request('/businesses/google-auth', { method: 'POST', body: JSON.stringify(payload) });
    if (res && res.access_token) {
      localStorage.setItem('callme_token', res.access_token);
    }
    return res;
  },
  createBusiness: async (data) => {
    const res = await request('/businesses', { method: 'POST', body: JSON.stringify(data) });
    if (res && res.access_token) {
      localStorage.setItem('callme_token', res.access_token);
    }
    return res;
  },
  updateBusiness: (id, data) => request(`/businesses/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteBusiness: (id) => request(`/businesses/${id}`, { method: 'DELETE' }),

  // FAQs
  getFaqs: (businessId) => request(`/businesses/${businessId}/faqs`),
  updateFaqs: (businessId, faqs) =>
    request(`/businesses/${businessId}/faqs`, {
      method: 'PUT',
      body: JSON.stringify({ faqs }),
    }),

  // Tools
  getTools: (businessId) => request(`/businesses/${businessId}/tools`),
  updateTools: (businessId, toolStatuses) =>
    request(`/businesses/${businessId}/tools`, {
      method: 'PUT',
      body: JSON.stringify({ tool_statuses: toolStatuses }),
    }),
  getToolDemands: (businessId) => request(`/businesses/${businessId}/tools/demands`),
  createToolDemand: (businessId, data) =>
    request(`/businesses/${businessId}/tools/demands`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Call History
  getCallHistory: (businessId, outcome = null) => {
    const query = outcome && outcome !== 'All' ? `?outcome=${encodeURIComponent(outcome)}` : '';
    return request(`/businesses/${businessId}/calls${query}`);
  },

  // Playground Chat
  sendMessage: (businessId, message) =>
    request(`/businesses/${businessId}/playground/messages`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  confirmAction: (businessId, actionId) =>
    request(`/businesses/${businessId}/pending-actions/${actionId}/confirm`, { method: 'POST' }),
  cancelAction: (businessId, actionId) =>
    request(`/businesses/${businessId}/pending-actions/${actionId}/cancel`, { method: 'POST' }),

  // Direct Web Voice Phone
  startWebCall: (businessId) =>
    request('/voice/web/start', {
      method: 'POST',
      body: JSON.stringify({ business_id: businessId }),
    }),
  sendWebCallTurn: async (sessionId, audioBlob, textFallback = '') => {
    const formData = new FormData();
    formData.append('session_id', sessionId);
    if (textFallback) {
      formData.append('text', textFallback);
      formData.append('text_fallback', textFallback);
    }
    if (audioBlob) {
      formData.append('audio', audioBlob, 'turn.wav');
      formData.append('audio_file', audioBlob, 'turn.wav');
    }
    const res = await fetch(`${API_BASE}/voice/web/turn`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Voice turn failed');
    }
    return res.json();
  },
  hangupWebCall: (sessionId) =>
    request('/voice/web/hangup', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    }),

  // Capability Setup Wizard & Integrations
  getCapabilities: (businessId) => request(`/businesses/${businessId}/capabilities`),
  getCapabilitySchema: (businessId, toolId) => request(`/businesses/${businessId}/capabilities/${toolId}/schema`),
  startCapabilitySetup: (businessId, toolId, optionId) =>
    request(`/businesses/${businessId}/capabilities/${toolId}/setup/start`, {
      method: 'POST',
      body: JSON.stringify({ option_id: optionId }),
    }),
  saveCapabilityStep: (businessId, toolId, stepName, data, isCompleted = false) =>
    request(`/businesses/${businessId}/capabilities/${toolId}/setup/save`, {
      method: 'POST',
      body: JSON.stringify({ step_name: stepName, data, is_completed: isCompleted }),
    }),
  validateCapabilitySetup: (businessId, toolId) =>
    request(`/businesses/${businessId}/capabilities/${toolId}/setup/validate`, { method: 'POST' }),
  activateCapability: (businessId, toolId) =>
    request(`/businesses/${businessId}/capabilities/${toolId}/activate`, { method: 'POST' }),
  deactivateCapability: (businessId, toolId) =>
    request(`/businesses/${businessId}/capabilities/${toolId}/deactivate`, { method: 'POST' }),
  disconnectCapability: (businessId, toolId) =>
    request(`/businesses/${businessId}/capabilities/${toolId}/integration`, { method: 'DELETE' }),
  testCapabilityConnection: (businessId, toolId) =>
    request(`/businesses/${businessId}/capabilities/${toolId}/test-connection`, { method: 'POST' }),

  // Resource Inventory & Reservations
  listResources: (businessId, resourceType = null) => {
    const q = resourceType ? `?resource_type=${encodeURIComponent(resourceType)}` : '';
    return request(`/businesses/${businessId}/resources${q}`);
  },
  createResource: (businessId, data) =>
    request(`/businesses/${businessId}/resources`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteResource: (businessId, resourceId) =>
    request(`/businesses/${businessId}/resources/${resourceId}`, { method: 'DELETE' }),
  listReservations: (businessId, status = null) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : '';
    return request(`/businesses/${businessId}/reservations${q}`);
  },
  createReservation: (businessId, data) =>
    request(`/businesses/${businessId}/reservations`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  cancelReservation: (businessId, reservationId, phone = null) => {
    const q = phone ? `?phone=${encodeURIComponent(phone)}` : '';
    return request(`/businesses/${businessId}/reservations/${reservationId}${q}`, { method: 'DELETE' });
  },

  // Restaurant Menu Management
  getMenu: (businessId, category = null) => {
    const q = category ? `?category=${encodeURIComponent(category)}` : '';
    return request(`/businesses/${businessId}/menu${q}`);
  },
  uploadMenu: (businessId, items, replace = true) =>
    request(`/businesses/${businessId}/menu/upload`, {
      method: 'POST',
      body: JSON.stringify({ items, replace }),
    }),
  deleteMenuItem: (businessId, itemId) =>
    request(`/businesses/${businessId}/menu/${itemId}`, { method: 'DELETE' }),
  searchMenu: (businessId, query) =>
    request(`/businesses/${businessId}/menu/search?query=${encodeURIComponent(query)}`, { method: 'POST' }),
  parseMenuText: (businessId, text, defaultCategory = 'Mains') =>
    request(`/businesses/${businessId}/menu/parse-text`, {
      method: 'POST',
      body: JSON.stringify({ text, default_category: defaultCategory }),
    }),

  // Admin Command Center
  getAdminOverview: () => request('/admin/overview'),
  getAdminTools: () => request('/admin/tools'),
  getAdminDemands: () => request('/admin/demands'),
  updateAdminDemandStatus: (demandId, status) =>
    request(`/admin/demands/${demandId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
};

export const getMenu = (businessId, category = null) => api.getMenu(businessId, category);
export const uploadMenu = (businessId, items, replace = true) => api.uploadMenu(businessId, items, replace);
export const deleteMenuItem = (businessId, itemId) => api.deleteMenuItem(businessId, itemId);
export const searchMenu = (businessId, query) => api.searchMenu(businessId, query);
export const parseMenuText = (businessId, text, defaultCategory = 'Mains') => api.parseMenuText(businessId, text, defaultCategory);

export default api;
