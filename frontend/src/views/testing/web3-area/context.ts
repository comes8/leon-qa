export type WorkspaceContext = { project?: string; workflow?: string; design?: string; env?: string; dataset?: string; job?: string };
const fields = ['project', 'workflow', 'design', 'env', 'dataset', 'job'] as const;
export function cleanContext(value: Record<string, unknown>): WorkspaceContext {
	const result: WorkspaceContext = {};
	for (const key of fields) {
		const entry = value?.[key];
		if (typeof entry === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(entry)) result[key] = entry;
		else if (typeof entry === 'number' && Number.isSafeInteger(entry) && entry > 0) result[key] = String(entry);
	}
	return result;
}
export function mergeContext(saved: WorkspaceContext, query: Record<string, unknown>): WorkspaceContext {
	const requested = cleanContext(query);
	const base = requested.project && requested.project !== saved.project ? {} : saved;
	return { ...base, ...requested };
}
export function readContext(user: unknown, query: Record<string, unknown>): WorkspaceContext {
	try {
		return mergeContext(cleanContext(JSON.parse(sessionStorage.getItem(`leon.web3.context.v1.${user}`) || '{}')), query);
	} catch {
		return cleanContext(query);
	}
}
export function saveContext(user: unknown, value: WorkspaceContext) {
	sessionStorage.setItem(`leon.web3.context.v1.${user}`, JSON.stringify(cleanContext(value)));
}
export function renderPrompt(content: string, inputs: Record<string, string>): string {
	return content.replace(/\{\{([^{}]+)\}\}/g, (whole, key) => (inputs[key]?.trim() ? inputs[key] : whole));
}
export const workflowPages = {
	requirements: { title: '需求与建模', help: '阅读需求、业务理解、变更范围与待确认事项' },
	testpoints: { title: '测试点设计', help: '核对覆盖矩阵、预期依据及待确认分支' },
	cases: { title: '用例与评审', help: '查看前置、步骤与预期，处理业务评审意见' },
	scenarios: { title: '接口场景', help: '检查接口关联、串行取值与断言，复核后发布' },
	execution: { title: '执行中心', help: '选择已有执行来源，确认环境后再提交' },
	reports: { title: '报告与证据', help: '按原运行查看实际结果；历史通过只代表当次运行' },
} as const;
export type WorkflowPage = keyof typeof workflowPages;
