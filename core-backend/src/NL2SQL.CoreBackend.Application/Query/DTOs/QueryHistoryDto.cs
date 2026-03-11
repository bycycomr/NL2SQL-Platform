namespace NL2SQL.CoreBackend.Application.Query.DTOs;

public record QueryHistoryDto(
    Guid Id,
    string DbId,
    string NaturalLanguageQuery,
    string? GeneratedSql,
    string? Explanation,
    string ExecutionStatus,
    int? ExecutionTimeMs,
    string? ErrorMessage,
    DateTime CreatedAt
);
