namespace NL2SQL.CoreBackend.Application.Query.DTOs;

public record GenerateSqlResponse(
    string Status,
    string? SqlQuery,
    string? Explanation,
    List<Dictionary<string, object>>? Data,
    string? Error,
    ValidationResult Validation,
    int? ExecutionTimeMs
);

public record ValidationResult(
    ValidationCheck SyntaxCheck,
    ValidationCheck SecurityCheck,
    ValidationCheck InjectionCheck,
    ValidationCheck CostCheck,
    ValidationCheck PermissionCheck
);

public record ValidationCheck(
    bool? Passed,
    string Message
);
