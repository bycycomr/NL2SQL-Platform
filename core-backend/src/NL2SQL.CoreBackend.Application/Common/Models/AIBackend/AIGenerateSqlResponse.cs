using System.Text.Json.Serialization;

namespace NL2SQL.CoreBackend.Application.Common.Models.AIBackend;

public class AIGenerateSqlResponse
{
    [JsonPropertyName("sql_query")]
    public string? SqlQuery { get; set; }

    [JsonPropertyName("explanation")]
    public string? Explanation { get; set; }

    [JsonPropertyName("data")]
    public List<Dictionary<string, object>>? Data { get; set; }

    [JsonPropertyName("error")]
    public string? Error { get; set; }

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;
}
