import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export const client = axios.create({ baseURL: API_BASE });

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("pulse_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const api = {
  register: (payload) => client.post("/api/v1/auth/register", payload).then((r) => r.data),
  login: (email, password) => {
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    return client
      .post("/api/v1/auth/login", form, { headers: { "Content-Type": "application/x-www-form-urlencoded" } })
      .then((r) => r.data);
  },
  me: () => client.get("/api/v1/auth/me").then((r) => r.data),

  listProjects: () => client.get("/api/v1/projects").then((r) => r.data),

  listQueues: (projectId) => client.get(`/api/v1/projects/${projectId}/queues`).then((r) => r.data),
  createQueue: (projectId, payload) => client.post(`/api/v1/projects/${projectId}/queues`, payload).then((r) => r.data),
  updateQueue: (projectId, queueId, payload) => client.patch(`/api/v1/projects/${projectId}/queues/${queueId}`, payload).then((r) => r.data),
  pauseQueue: (projectId, queueId) => client.post(`/api/v1/projects/${projectId}/queues/${queueId}/pause`).then((r) => r.data),
  resumeQueue: (projectId, queueId) => client.post(`/api/v1/projects/${projectId}/queues/${queueId}/resume`).then((r) => r.data),
  queueStats: (projectId, queueId) => client.get(`/api/v1/projects/${projectId}/queues/${queueId}/stats`).then((r) => r.data),

  listJobs: (projectId, queueId, params) => client.get(`/api/v1/projects/${projectId}/queues/${queueId}/jobs`, { params }).then((r) => r.data),
  createJob: (projectId, queueId, payload) => client.post(`/api/v1/projects/${projectId}/queues/${queueId}/jobs`, payload).then((r) => r.data),
  jobExecutions: (projectId, queueId, jobId) => client.get(`/api/v1/projects/${projectId}/queues/${queueId}/jobs/${jobId}/executions`).then((r) => r.data),
  jobLogs: (projectId, queueId, jobId) => client.get(`/api/v1/projects/${projectId}/queues/${queueId}/jobs/${jobId}/logs`).then((r) => r.data),
  cancelJob: (projectId, queueId, jobId) => client.post(`/api/v1/projects/${projectId}/queues/${queueId}/jobs/${jobId}/cancel`).then((r) => r.data),
  retryJob: (projectId, queueId, jobId) => client.post(`/api/v1/projects/${projectId}/queues/${queueId}/jobs/${jobId}/retry`).then((r) => r.data),

  listWorkers: (apiKey) => client.get("/api/v1/workers", { headers: { "x-api-key": apiKey } }).then((r) => r.data),

  deadLetters: (projectId) => client.get(`/api/v1/projects/${projectId}/dead-letter`).then((r) => r.data),
  replayDeadLetter: (projectId, dlqId) => client.post(`/api/v1/projects/${projectId}/dead-letter/${dlqId}/replay`).then((r) => r.data),

  overview: (projectId) => client.get(`/api/v1/projects/${projectId}/stats/overview`).then((r) => r.data),
  throughput: (projectId, hours = 24) => client.get(`/api/v1/projects/${projectId}/stats/throughput`, { params: { hours } }).then((r) => r.data),
};
