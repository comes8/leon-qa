import request from '/@/utils/request';
const root = '/v1/Ntesterc_web3/interfaces';
const data = async (config: any) => ((await request(config)) as any).data;
export const interfaceApi = {
	options: (project: string) => data({ url: root + '/options', params: { project_id: project } }),
	list: (project: string) => data({ url: root + '/plans', params: { project_id: project } }),
	detail: (id: number) => data({ url: `${root}/plans/${id}` }),
	create: (body: any) => data({ url: root + '/plans', method: 'POST', data: body }),
	preview: (id: number, body: any) => data({ url: `${root}/plans/${id}/preview`, method: 'POST', data: body }),
	generate: (id: number, body: any) => data({ url: `${root}/plans/${id}/generate`, method: 'POST', data: body }),
	revise: (id: number, body: any) => data({ url: `${root}/plans/${id}/revisions`, method: 'POST', data: body }),
	publish: (id: number, body: any) => data({ url: `${root}/plans/${id}/publish`, method: 'POST', data: body }),
	run: (id: number, body: any) => data({ url: `${root}/plans/${id}/run`, method: 'POST', data: body }),
	job: (id: number, job: number) => data({ url: `${root}/plans/${id}/jobs/${job}` }),
	cancel: (id: number, job: number, note: string) => data({ url: `${root}/plans/${id}/jobs/${job}/cancel`, method: 'POST', data: { note } }),
	export: (id: number) => request({ url: `${root}/plans/${id}/export` }),
};
export { interfaceVerdict, validInterfaceExport } from './interface-state';
