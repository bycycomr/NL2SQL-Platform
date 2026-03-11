using System.Text.Json.Serialization;

namespace NL2SQL.CoreBackend.Application.Common.Models.AIBackend;

public class AIRegisterSchemaResponse
{
    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("db_id")]
    public string DbId { get; set; } = string.Empty;

    [JsonPropertyName("chunks_saved")]
    public int ChunksSaved { get; set; }
}
