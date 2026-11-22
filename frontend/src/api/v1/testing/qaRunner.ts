import request from '/@/utils/request';
import type { RunnerApi, Catalog, Job, RunnerEvent, LogPage, CreateJob } from '/@/views/testing/qa-runner/types';

const base = '/v1/Ntesterc_qa_runner';
type Envelope<T> = { data: T };
async function get<T>(url: string, params?: Record<string, unknown>) {
  return (await request<unknown, Envelope<T>>({ url: base + url, params })).data;
}
export const runnerApi: RunnerApi = {
  catalog: () => get<Catalog>('/catalog'),
  jobs: async project => (await get<{ items: Job[] }>('/jobs', { project_id: project, limit: 100 })).items,
  job: id => get<Job>('/jobs/' + id),
  submit: async (body: CreateJob) => (await request<unknown, Envelope<{ job: Job; duplicate: boolean }>>({
    url: base + '/jobs', method: 'POST', data: body, timeout: 15000,
  })).data,
  cancel: async id => (await request<unknown, Envelope<Job>>({ url: `${base}/jobs/${id}/cancel`, method: 'POST' })).data,
  events: (id, after) => get<{ items: RunnerEvent[]; next_after: number }>(`/jobs/${id}/events`, { after, limit: 200 }),
  logs: (id, stream, offset) => get<LogPage>(`/jobs/${id}/logs`, { stream, offset, limit: 65536 }),
  artifact: (id, relative) => request<unknown, Blob>({
    url: `${base}/jobs/${id}/artifacts/${relative.split('/').map(encodeURIComponent).join('/')}`, responseType: 'blob',
  }),
};
