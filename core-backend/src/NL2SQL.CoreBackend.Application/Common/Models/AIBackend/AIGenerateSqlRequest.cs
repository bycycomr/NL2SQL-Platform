using System.Text.Json.Serialization;

namespace NL2SQL.CoreBackend.Application.Common.Models.AIBackend;

public class AIGenerateSqlRequest
{
    [JsonPropertyName("db_id")]
    public string DbId { get; set; } = string.Empty;

    [JsonPropertyName("connection_string")]
    public string ConnectionString { get; set; } = string.Empty;

    [JsonPropertyName("query")]
    public string Query { get; set; } = string.Empty;

    [JsonPropertyName("user_id")]
    public string? UserId { get; set; }
}
