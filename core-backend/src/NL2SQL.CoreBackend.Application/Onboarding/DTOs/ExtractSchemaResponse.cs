namespace NL2SQL.CoreBackend.Application.Onboarding.DTOs;

public record ExtractSchemaResponse(
    string DbId,
    List<TableSchemaDto> Tables
);

public record TableSchemaDto(
    string Name,
    List<string> Columns,
    string HumanDescription = "",
    string BusinessRules = ""
);
