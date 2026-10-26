/**
 * CallMe REST API Client
 * Connects React frontend directly to FastAPI backend.
 */

const API_BASE = '/api';

async function request(path, options = {}) {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  try {
    const res = await fetch(url, {
      ...options,
      headers: options.body instanceof FormData ? options.headers : headers,
    });

    if (!res.ok) {
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
  loginBusiness: (email, password) =>
    request('/businesses/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  accessBusiness: (identifier) =>
    request('/businesses/access', { method: 'POST', body: JSON.stringify({ identifier }) }),
  googleAuth: (payload) =>
    request('/businesses/google-auth', { method: 'POST', body: JSON.stringify(payload) }),
  createBusiness: (data) => request('/businesses', { method: 'POST', body: JSON.stringify(data) }),
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
