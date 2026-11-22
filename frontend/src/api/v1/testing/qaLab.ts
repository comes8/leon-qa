import request from '/@/utils/request';
import type { LabApi, LabView, Operation } from '/@/views/testing/qa-lab/model';
const root = '/v1/Ntesterc_qa_runner/lab';
export const labApi: LabApi = {
  state: async project => (await request<unknown, { data: LabView }>({ url: root + '/state', params: { project_id: project } })).data,
  submit: async body => (await request<unknown, { data: { operation: Operation; duplicate: boolean } }>({
    url: root + '/operations', method: 'POST', data: body, timeout: 15000,
  })).data,
};
