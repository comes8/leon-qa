export type StageDefinition = { title: string; skill: string; prompts: string[]; role: string; page: string };
export type DesignState = { project: string; options: any; tasks: any[]; task: any; loading: boolean; error: string };
export const initialDesignState = (): DesignState => ({
	project: '',
	options: { stages: {}, bundles: [], models: [], knowledge: [] },
	tasks: [],
	task: null,
	loading: false,
	error: '',
});
export function errorText(error: any): string {
	const detail = error?.response?.data?.detail;
	if (typeof detail === 'string') return detail;
	if (Array.isArray(detail))
		return detail
			.slice(0, 8)
			.map((d: any) => `${(d.loc || []).join('.')}: ${d.msg || '输入无效'}`)
			.join('；');
	return error?.message || '请求失败';
}
export function createDesignController(
	state: DesignState,
	api: { options: (p: string) => Promise<any>; list: (p: string) => Promise<any>; detail: (id: number) => Promise<any> }
) {
	let projectEpoch = 0,
		selectionEpoch = 0,
		requestEpoch = 0,
		alive = true;
	return {
		async project(project: string, requested?: string) {
			const epoch = ++projectEpoch;
			++selectionEpoch;
			++requestEpoch;
			state.project = project;
			state.task = null;
			state.tasks = [];
			state.options = { stages: {}, bundles: [], models: [], knowledge: [] };
			state.error = '';
			state.loading = true;
			try {
				const [options, tasks] = await Promise.all([api.options(project), api.list(project)]);
				if (!alive || epoch !== projectEpoch) return;
				state.options = options;
				state.tasks = tasks;
				const id = requested && /^[1-9]\d*$/.test(requested) ? Number(requested) : tasks[0]?.id;
				if (id) await this.select(id);
			} catch (e) {
				if (alive && epoch === projectEpoch) state.error = errorText(e);
			} finally {
				if (alive && epoch === projectEpoch) state.loading = false;
			}
		},
		async select(id: number) {
			const selection = ++selectionEpoch,
				project = projectEpoch,
				request = ++requestEpoch;
			state.task = null;
			state.error = '';
			try {
				const task = await api.detail(id);
				if (!alive || project !== projectEpoch || selection !== selectionEpoch || request !== requestEpoch) return;
				if (String(task.project_id) !== state.project) throw new Error('此业务设计不属于当前项目，请重新选择');
				state.task = task;
			} catch (e) {
				if (alive && project === projectEpoch && selection === selectionEpoch) state.error = errorText(e);
			}
		},
		async refresh() {
			if (!state.task) return;
			const id = state.task.id,
				selection = selectionEpoch,
				project = projectEpoch,
				request = ++requestEpoch;
			try {
				const task = await api.detail(id);
				if (!alive || project !== projectEpoch || selection !== selectionEpoch || request !== requestEpoch) return;
				if (String(task.project_id) !== state.project) throw new Error('此业务设计不属于当前项目，请重新选择');
				state.task = task;
				state.error = '';
				const tasks = await api.list(state.project);
				if (alive && project === projectEpoch && selection === selectionEpoch && request === requestEpoch) state.tasks = tasks;
			} catch (e) {
				if (alive && project === projectEpoch && selection === selectionEpoch) state.error = errorText(e);
			}
		},
		accept(task: any) {
			++requestEpoch;
			if (alive && String(task.project_id) === state.project) state.task = task;
		},
		dispose() {
			alive = false;
			++projectEpoch;
			++selectionEpoch;
			++requestEpoch;
		},
	};
}
export const readinessLabel = (value: string) => ({ ready: '设计就绪', partial: '部分待确认', blocked: '关键判据受阻' }[value] || value);
export const preparationLabel = (value: string) =>
	({ known_available: '材料已说明具备', needs_preparation: '执行需准备', capability_unknown: '能力待核对' }[value] || value);
export function requestUncertain(error: any) {
	const status = error?.response?.status;
	return !status || status >= 500 || status === 408;
}

export function assertDesignExport(value: any, taskId: number) {
	if (!value || value.id !== taskId || !Array.isArray(value.all_artifacts) || !Array.isArray(value.all_inputs)) {
		throw new Error('导出内容不完整或不属于当前任务，请刷新后重试；未生成下载文件。');
	}
	return value;
}
