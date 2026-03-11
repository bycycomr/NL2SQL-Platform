namespace NL2SQL.CoreBackend.Application.Onboarding.DTOs;

public record RegisterSchemaResponse(
    string Status,
    string DbId,
    string Message,
    int ChunksSaved
);
