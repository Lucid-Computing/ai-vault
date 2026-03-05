const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
	const resp = await fetch(`${BASE}${path}`, {
		headers: { 'Content-Type': 'application/json' },
		...options
	});
	if (!resp.ok) {
		const err = await resp.json().catch(() => ({ detail: resp.statusText }));
		throw new Error(err.detail || resp.statusText);
	}
	if (resp.status === 204) return undefined as T;
	return resp.json();
}

export const api = {
	// Resources
	listResources: (params?: Record<string, string>) => {
		const qs = params ? '?' + new URLSearchParams(params).toString() : '';
		return request<any[]>(`/resources${qs}`);
	},
	createResource: (data: any) =>
		request<any>('/resources', { method: 'POST', body: JSON.stringify(data) }),
	updateResource: (id: string, data: any) =>
		request<any>(`/resources/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
	deleteResource: (id: string) =>
		request<void>(`/resources/${id}`, { method: 'DELETE' }),

	// Rules
	listRules: (resourceId?: string) => {
		const qs = resourceId ? `?resource_id=${resourceId}` : '';
		return request<any[]>(`/rules${qs}`);
	},
	createRule: (data: any) =>
		request<any>('/rules', { method: 'POST', body: JSON.stringify(data) }),
	deleteRule: (id: string) =>
		request<void>(`/rules/${id}`, { method: 'DELETE' }),

	// Activity
	listActivity: (limit = 50) => request<any[]>(`/activity?limit=${limit}`),

	// Approvals
	listApprovals: (status?: string) => {
		const qs = status ? `?status=${status}` : '';
		return request<any[]>(`/approvals${qs}`);
	},
	approveRequest: (id: string, reason?: string) =>
		request<any>(`/approvals/${id}/approve`, {
			method: 'POST',
			body: JSON.stringify({ reason })
		}),
	denyRequest: (id: string, reason?: string) =>
		request<any>(`/approvals/${id}/deny`, {
			method: 'POST',
			body: JSON.stringify({ reason })
		}),

	// Overview
	getOverview: () => request<any>('/overview')
};
