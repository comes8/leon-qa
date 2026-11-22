import request from '/@/utils/request';
const root = '/v1/Ntesterc_web3/design';
const data = async (config: any) => ((await request(config)) as any).data;
export const designApi = {
	options: (project: string) => data({ url: root + '/options', params: { project_id: project } }),
	list: (project: string) => data({ url: root + '/tasks', params: { project_id: project } }),
	detail: (id: number) => data({ url: `${root}/tasks/${id}` }),
	create: (body: any) => data({ url: root + '/tasks', method: 'POST', data: body }),
	update: (id: number, body: any) => data({ url: `${root}/tasks/${id}`, method: 'PUT', data: body }),
	preview: (id: number, body: any) => data({ url: `${root}/tasks/${id}/preview`, method: 'POST', data: body }),
	generate: (id: number, body: any) => data({ url: `${root}/tasks/${id}/stages`, method: 'POST', data: body }),
	confirm: (id: number, body: any) => data({ url: `${root}/tasks/${id}/confirm`, method: 'POST', data: body }),
	revise: (id: number, body: any) => data({ url: `${root}/tasks/${id}/revisions`, method: 'POST', data: body }),
	manual: (id: number, body: any) => data({ url: `${root}/tasks/${id}/manual`, method: 'POST', data: body }),
	artifact: (id: number, artifact: number) => data({ url: `${root}/tasks/${id}/artifacts/${artifact}` }),
	job: (id: number, job: number) => data({ url: `${root}/tasks/${id}/jobs/${job}` }),
	input: (id: number, revision: number) => data({ url: `${root}/tasks/${id}/inputs/${revision}` }),
	// Export returns a standalone JSON document, without the normal data envelope.
	export: (id: number) => request({ url: `${root}/tasks/${id}/export` }),
};
