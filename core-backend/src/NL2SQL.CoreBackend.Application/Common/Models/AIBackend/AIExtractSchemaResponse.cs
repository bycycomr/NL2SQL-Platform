using System.Text.Json.Serialization;

namespace NL2SQL.CoreBackend.Application.Common.Models.AIBackend;

public class AIExtractSchemaResponse
{
    [JsonPropertyName("db_id")]
    public string DbId { get; set; } = string.Empty;

    [JsonPropertyName("tables")]
    public List<AITableSchema> Tables { get; set; } = [];

    [JsonPropertyName("few_shot_examples")]
    public List<Dictionary<string, string>> FewShotExamples { get; set; } = [];
}

public class AITableSchema
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("columns")]
    public List<string> Columns { get; set; } = [];

    [JsonPropertyName("human_description")]
    public string HumanDescription { get; set; } = string.Empty;

    [JsonPropertyName("business_rules")]
    public string BusinessRules { get; set; } = string.Empty;
}
