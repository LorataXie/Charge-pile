const API_BASE = 'http://localhost:8000/api/v1';

function getToken() {
    return localStorage.getItem('token');
}

function setToken(token) {
    localStorage.setItem('token', token);
}

function clearToken() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
}

async function api(path, options = {}) {
    const token = getToken();
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (res.status === 401) {
        clearToken();
        window.location.reload();
        throw new Error('Unauthorized');
    }
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status}`);
    }
    return data;
}

const API = {
    // Auth
    register: (username, password, role) => api('/auth/register', { method: 'POST', body: JSON.stringify({ username, password, role }) }),
    login: (username, password) => api('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
    getMe: () => api('/auth/me'),

    // Orders
    listMyOrders: () => api('/orders'),
    getOrder: (orderId) => api(`/orders/${orderId}`),
    submitOrder: (vehicle_id, mode, requested_kwh) => api('/orders', { method: 'POST', body: JSON.stringify({ vehicle_id, mode, requested_kwh }) }),
    modifyOrder: (orderId, data) => api(`/orders/${orderId}`, { method: 'PUT', body: JSON.stringify(data) }),
    cancelOrder: (orderId) => api(`/orders/${orderId}`, { method: 'DELETE' }),
    endCharging: (orderId) => api(`/orders/${orderId}/end`, { method: 'POST' }),
    getDetail: (orderId) => api(`/orders/${orderId}/detail`),

    // Queue
    getQueueStatus: (orderId) => api(`/queue/status/${orderId}`),
    getWaitingArea: () => api('/queue/waiting-area'),

    // Piles
    listPiles: () => api('/piles'),
    getPile: (pileId) => api(`/piles/${pileId}`),
    startPile: (pileId) => api(`/piles/${pileId}/start`, { method: 'POST' }),
    stopPile: (pileId) => api(`/piles/${pileId}/stop`, { method: 'POST' }),

    // Faults
    reportFault: (pileId, strategy) => api(`/faults/${pileId}`, { method: 'POST', body: JSON.stringify({ strategy }) }),
    recoverPile: (pileId) => api(`/faults/${pileId}/recover`, { method: 'POST' }),
    listFaults: () => api('/faults'),

    // Reports
    generateReport: (report_type) => api('/reports', { method: 'POST', body: JSON.stringify({ report_type }) }),
    listReports: () => api('/reports'),
    getReport: (reportId) => api(`/reports/${reportId}`),

    // Vehicles
    listMyVehicles: () => api('/vehicles'),
    createVehicle: (license_plate, battery_capacity) => api('/vehicles', { method: 'POST', body: JSON.stringify({ license_plate, battery_capacity }) }),

    // Billing
    getRules: () => api('/billing/rules'),

    // Sim
    getClock: () => api('/sim/clock'),
    tick: () => api('/sim/tick', { method: 'POST' }),
};
