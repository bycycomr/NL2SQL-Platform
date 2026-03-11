using System.Text.Json.Serialization;

namespace NL2SQL.CoreBackend.Application.Common.Models.AIBackend;

public class AIExtractSchemaRequest
{
    [JsonPropertyName("db_id")]
    public string DbId { get; set; } = string.Empty;

    [JsonPropertyName("connection_string")]
    public string ConnectionString { get; set; } = string.Empty;
}
