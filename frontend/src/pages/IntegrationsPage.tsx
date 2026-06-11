import {
  capabilityStatusLabel,
  capabilityTitle,
  DataError,
  DataLoading,
  isCapabilityConnected,
  MetricStrip,
  PageHeader,
  SectionPanel,
  useActiveProjectId,
  useWorkspaceData,
} from "./projectWorkspace";

export function IntegrationsPage() {
  const projectId = useActiveProjectId();
  const data = useWorkspaceData({ projectId, includeIntegrations: true });

  if (data.loading) return <DataLoading />;
  if (data.error) return <DataError message={data.error} onRetry={data.reload} />;

  const capabilities = data.integrations?.capabilities ?? [];
  const services = data.integrations?.services ?? [];
  const connectedCount = capabilities.filter((capability) => isCapabilityConnected(capability)).length;
  const actionRequiredCount = capabilities.filter((capability) =>
    ["disabled", "missing_key", "missing_tool", "manual_setup", "not_configured"].includes(capability.status),
  ).length;

  return (
    <div className="pb-8">
      <PageHeader
        title="系统设置"
        subtitle="查看后端能力接入状态。页面只展示能力名、连接状态和代码路径，不展示任何密钥。"
      />

      <MetricStrip
        items={[
          { label: "能力数量", value: capabilities.length, helper: "GET /integrations/status" },
          { label: "已接入", value: connectedCount, helper: "active / available", tone: "text-[#16A34A]" },
          { label: "待处理状态", value: actionRequiredCount, helper: "缺工具 / 手工设置 / 未接入", tone: "text-[#F59E0B]" },
          { label: "服务记录", value: services.length, helper: "后端 services 数组" },
        ]}
      />

      {data.optionalErrors.integrations ? (
        <div className="mb-5 rounded-[12px] border border-[#FECACA] bg-[#FEF2F2] px-4 py-3 text-[13px] text-[#EF4444]">
          集成状态读取失败：{data.optionalErrors.integrations}
        </div>
      ) : null}

      <SectionPanel title="能力接入状态" subtitle="这些状态会影响岗位分析、找候选人、评估、触达和周报按钮是否可用。">
        {capabilities.length === 0 ? (
          <div className="text-[13px] text-[#6B7280]">后端没有返回能力状态。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-[840px] w-full text-left text-[13px] leading-5">
              <thead className="h-11 bg-[#F9FAFB] text-[12px] font-semibold text-[#6B7280]">
                <tr>
                  <th className="w-[220px] px-4">能力</th>
                  <th className="w-[160px] px-3">服务类型</th>
                  <th className="w-[120px] px-3">状态</th>
                  <th className="w-[180px] px-3">连接名称</th>
                  <th className="px-4">代码路径</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#EEF2F7]">
                {capabilities.map((capability) => (
                  <tr key={capability.id}>
                    <td className="px-4 py-4">
                      <div className="font-semibold text-[#111827]">{capabilityTitle(capability)}</div>
                      <div className="mt-1 text-[12px] text-[#9CA3AF]">{capability.id}</div>
                    </td>
                    <td className="px-3 py-4 text-[#374151]">{capability.service_type}</td>
                    <td className="px-3 py-4">
                      <span
                        className={[
                          "inline-flex rounded-full px-2 py-0.5 text-[12px] font-medium leading-[18px]",
                          isCapabilityConnected(capability)
                            ? "bg-[#ECFDF3] text-[#16A34A]"
                            : "bg-[#FFFBEB] text-[#F59E0B]",
                        ].join(" ")}
                      >
                        {capabilityStatusLabel(capability.status)}
                      </span>
                    </td>
                    <td className="px-3 py-4 text-[#374151]">{capability.connected_name_zh ?? "—"}</td>
                    <td className="px-4 py-4 text-[#374151]">{capability.code_path ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionPanel>

      <div className="mt-5">
        <SectionPanel title="服务明细" subtitle="来自 config/services.toml 的当前注册 service；旧占位项不会进入这张表。">
          {services.length === 0 ? (
            <div className="text-[13px] text-[#6B7280]">后端没有返回服务明细。</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-[980px] w-full text-left text-[13px] leading-5">
                <thead className="h-11 bg-[#F9FAFB] text-[12px] font-semibold text-[#6B7280]">
                  <tr>
                    <th className="w-[260px] px-4">Service</th>
                    <th className="w-[140px] px-3">类型</th>
                    <th className="w-[180px] px-3">Provider</th>
                    <th className="w-[120px] px-3">状态</th>
                    <th className="w-[90px] px-3">默认</th>
                    <th className="px-4">代码路径</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#EEF2F7]">
                  {services.map((service) => {
                    const name = readServiceString(service, "name") || "unknown_service";
                    const status = readServiceString(service, "status") || "unknown";
                    const isConnected = status === "active" || status === "available";
                    return (
                      <tr key={name}>
                        <td className="px-4 py-4">
                          <div className="font-semibold text-[#111827]">{readServiceString(service, "name_zh") || name}</div>
                          <div className="mt-1 text-[12px] text-[#9CA3AF]">{name}</div>
                        </td>
                        <td className="px-3 py-4 text-[#374151]">{readServiceString(service, "type") || "—"}</td>
                        <td className="px-3 py-4 text-[#374151]">{readServiceString(service, "provider") || "—"}</td>
                        <td className="px-3 py-4">
                          <span
                            className={[
                              "inline-flex rounded-full px-2 py-0.5 text-[12px] font-medium leading-[18px]",
                              isConnected ? "bg-[#ECFDF3] text-[#16A34A]" : "bg-[#FFFBEB] text-[#F59E0B]",
                            ].join(" ")}
                          >
                            {capabilityStatusLabel(status)}
                          </span>
                        </td>
                        <td className="px-3 py-4 text-[#374151]">{readServiceBool(service, "is_default") ? "是" : "否"}</td>
                        <td className="px-4 py-4 text-[#374151]">{readServiceString(service, "code_path") || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </SectionPanel>
      </div>
    </div>
  );
}

function readServiceString(service: Record<string, unknown>, key: string) {
  const value = service[key];
  return typeof value === "string" ? value : null;
}

function readServiceBool(service: Record<string, unknown>, key: string) {
  return service[key] === true;
}
