namespace NL2SQL.CoreBackend.Application.Query.DTOs;

public record GenerateSqlRequest(
    string Query,
    string DbId
);
