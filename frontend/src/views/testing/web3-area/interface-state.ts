export function interfaceVerdict(receipt: any, status?: string) {
	if (status && ['interrupted', 'cancelled', 'failed'].includes(status)) return '执行受阻或中断，请核对已有证据';
	if (!receipt) return '尚无执行证据';
	if (!receipt.finished_at) return '执行未完成';
	return receipt.failed_cases ? '存在失败用例' : receipt.passed_cases > 0 ? '当次范围通过' : '没有通过证明';
}
export function validInterfaceExport(value: any, id: number) {
	if (value?.id !== id || !value?.snapshot?.business_binding || !Array.isArray(value?.jobs)) throw new Error('接口记录导出不完整，未生成下载');
	return value;
}
