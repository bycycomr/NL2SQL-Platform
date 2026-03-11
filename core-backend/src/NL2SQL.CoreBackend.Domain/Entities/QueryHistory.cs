using NL2SQL.CoreBackend.Domain.Common;
using NL2SQL.CoreBackend.Domain.Enums;

namespace NL2SQL.CoreBackend.Domain.Entities;

public class QueryHistory : BaseEntity
{
    public Guid UserId { get; set; }
    public string DbId { get; set; } = string.Empty;
    public string NaturalLanguageQuery { get; set; } = string.Empty;
    public string? GeneratedSql { get; set; }
    public string? Explanation { get; set; }
    public ExecutionStatus ExecutionStatus { get; set; } = ExecutionStatus.Pending;
    public int? ExecutionTimeMs { get; set; }
    public string? ErrorMessage { get; set; }
    public string? ResultDataJson { get; set; }

    public User User { get; set; } = null!;
}
