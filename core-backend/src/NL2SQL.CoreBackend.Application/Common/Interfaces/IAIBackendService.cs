using NL2SQL.CoreBackend.Application.Common.Models.AIBackend;

namespace NL2SQL.CoreBackend.Application.Common.Interfaces;

public interface IAIBackendService
{
    Task<AIGenerateSqlResponse> GenerateSqlAsync(
        AIGenerateSqlRequest request, CancellationToken ct = default);

    Task<AIExtractSchemaResponse> ExtractSchemaAsync(
        AIExtractSchemaRequest request, CancellationToken ct = default);

    Task<AIRegisterSchemaResponse> RegisterSchemaAsync(
        AIRegisterSchemaRequest request, CancellationToken ct = default);

    Task<bool> HealthCheckAsync(CancellationToken ct = default);
}
