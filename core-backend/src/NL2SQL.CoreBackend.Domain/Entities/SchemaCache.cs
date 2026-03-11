using NL2SQL.CoreBackend.Domain.Common;

namespace NL2SQL.CoreBackend.Domain.Entities;

public class SchemaCache : BaseEntity
{
    public string DbId { get; set; } = string.Empty;
    public string DatabaseName { get; set; } = string.Empty;
    public string SchemaJson { get; set; } = "{}";
    public DateTime ExpiresAt { get; set; } = DateTime.UtcNow.AddHours(1);
}
