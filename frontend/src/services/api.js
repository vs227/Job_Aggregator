const rawBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const BASE_URL = rawBaseUrl.endsWith('/') ? rawBaseUrl.slice(0, -1) : rawBaseUrl;

function getHeaders() {
  const token = localStorage.getItem('token');
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

async function request(endpoint, options = {}) {
  let res;
  try {
    res = await fetch(`${BASE_URL}${endpoint}`, {
      headers: getHeaders(),
      ...options,
    });
  } catch (err) {
    console.error("Fetch network error:", err);
    throw new Error(`Network connection error. Is the backend server running at ${BASE_URL}?`);
  }

  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  let data;
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      data = await res.json();
    } catch (err) {
      console.error("JSON parsing error:", err);
      throw new Error("Invalid response format received from server.");
    }
  } else {
    const text = await res.text();
    console.error("Non-JSON response received:", text);
    throw new Error(`Server error (${res.status}): ${text.substring(0, 100)}`);
  }

  if (!res.ok) {
    throw new Error(data?.detail || 'Something went wrong');
  }

  return data;
}

export function registerUser(username, email, password) {
  return request('/register', {
    method: 'POST',
    body: JSON.stringify({ username, email, password }),
  });
}

export function loginUser(email, password) {
  return request('/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export function fetchProfile() {
  return request('/profile');
}

export function fetchJobs(page = 1, perPage = 12) {
  return request(`/get_jobs?page=${page}&per_page=${perPage}`);
}

export function searchJobs(filters, page = 1, perPage = 12) {
  return request(`/search_jobs?page=${page}&per_page=${perPage}`, {
    method: 'POST',
    body: JSON.stringify(filters),
  });
}

export function fetchJob(jobId) {
  return request(`/jobs/${jobId}`);
}

export function saveJob(jobId) {
  return request('/save_job', {
    method: 'POST',
    body: JSON.stringify({ job_id: jobId }),
  });
}

export function fetchSavedJobs() {
  return request('/saved_jobs');
}

export function unsaveJob(jobId) {
  return request(`/saved_jobs/${jobId}`, { method: 'DELETE' });
}

export function fetchAlerts() {
  return request('/alert_preferences');
}

export function createAlert(alertData) {
  return request('/alert_preferences', {
    method: 'POST',
    body: JSON.stringify(alertData),
  });
}

export function deleteAlert(alertId) {
  return request(`/alert_preferences/${alertId}`, { method: 'DELETE' });
}

export function fetchSources() {
  return request('/job_sources');
}

export function fetchLocations() {
  return request('/locations');
}

export async function uploadResume(file) {
  const formData = new FormData();
  formData.append('file', file);
  const token = localStorage.getItem('token');
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${BASE_URL}/resume/upload`, {
    method: 'POST',
    headers,
    body: formData
  });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to upload resume');
  return data;
}

export function chatWithResume(message) {
  return request('/resume/chat', {
    method: 'POST',
    body: JSON.stringify({ message })
  });
}
