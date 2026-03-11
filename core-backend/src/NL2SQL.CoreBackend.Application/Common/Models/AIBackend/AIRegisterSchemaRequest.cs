using System.Text.Json.Serialization;

namespace NL2SQL.CoreBackend.Application.Common.Models.AIBackend;

public class AIRegisterSchemaRequest
{
    [JsonPropertyName("db_id")]
    public string DbId { get; set; } = string.Empty;

    [JsonPropertyName("tables")]
    public List<AITableSchema> Tables { get; set; } = [];

    [JsonPropertyName("few_shot_examples")]
    public List<AIFewShotExample> FewShotExamples { get; set; } = [];
}

public class AIFewShotExample
{
    [JsonPropertyName("question")]
    public string Question { get; set; } = string.Empty;

    [JsonPropertyName("query")]
    public string Query { get; set; } = string.Empty;
}
