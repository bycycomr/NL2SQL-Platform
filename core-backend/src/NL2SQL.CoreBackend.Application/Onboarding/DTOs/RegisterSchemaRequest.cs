namespace NL2SQL.CoreBackend.Application.Onboarding.DTOs;

public record RegisterSchemaRequest(
    string DbId,
    List<TableSchemaDto> Tables,
    List<FewShotExampleDto> FewShotExamples
);

public record FewShotExampleDto(
    string Question,
    string Query
);
