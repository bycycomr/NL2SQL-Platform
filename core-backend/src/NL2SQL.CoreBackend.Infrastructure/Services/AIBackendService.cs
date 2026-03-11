using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using NL2SQL.CoreBackend.Application.Common.Interfaces;
using NL2SQL.CoreBackend.Application.Common.Models.AIBackend;

namespace NL2SQL.CoreBackend.Infrastructure.Services;

public sealed class AIBackendService : IAIBackendService
{
    private readonly HttpClient _http;
    private readonly ILogger<AIBackendService> _logger;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true
    };

    public AIBackendService(HttpClient http, ILogger<AIBackendService> logger)
    {
        _http = http;
        _logger = logger;
    }

    public async Task<AIGenerateSqlResponse> GenerateSqlAsync(
        AIGenerateSqlRequest request, CancellationToken ct = default)
    {
        _logger.LogInformation("AI Backend'e SQL üretim isteği gönderiliyor — db_id: {DbId}", request.DbId);

        var response = await _http.PostAsJsonAsync("/api/v1/query/generate", request, JsonOptions, ct);
        response.EnsureSuccessStatusCode();

        var result = await response.Content.ReadFromJsonAsync<AIGenerateSqlResponse>(JsonOptions, ct);
        return result ?? throw new InvalidOperationException("AI Backend boş yanıt döndü.");
    }

    public async Task<AIExtractSchemaResponse> ExtractSchemaAsync(
        AIExtractSchemaRequest request, CancellationToken ct = default)
    {
        _logger.LogInformation("AI Backend'e şema çıkarma isteği gönderiliyor — db_id: {DbId}", request.DbId);

        var response = await _http.PostAsJsonAsync("/api/v1/onboarding/extract", request, JsonOptions, ct);
        response.EnsureSuccessStatusCode();

        var result = await response.Content.ReadFromJsonAsync<AIExtractSchemaResponse>(JsonOptions, ct);
        return result ?? throw new InvalidOperationException("AI Backend boş yanıt döndü.");
    }

    public async Task<AIRegisterSchemaResponse> RegisterSchemaAsync(
        AIRegisterSchemaRequest request, CancellationToken ct = default)
    {
        _logger.LogInformation("AI Backend'e şema kayıt isteği gönderiliyor — db_id: {DbId}", request.DbId);

        var response = await _http.PostAsJsonAsync("/api/v1/onboarding/register", request, JsonOptions, ct);
        response.EnsureSuccessStatusCode();

        var result = await response.Content.ReadFromJsonAsync<AIRegisterSchemaResponse>(JsonOptions, ct);
        return result ?? throw new InvalidOperationException("AI Backend boş yanıt döndü.");
    }

    public async Task<bool> HealthCheckAsync(CancellationToken ct = default)
    {
        try
        {
            var response = await _http.GetAsync("/health", ct);
            return response.IsSuccessStatusCode;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "AI Backend sağlık kontrolü başarısız");
            return false;
        }
    }
}
