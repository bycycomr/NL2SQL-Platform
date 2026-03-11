namespace NL2SQL.CoreBackend.Application.Auth.DTOs;

public record UserDto(
    Guid Id,
    string Email,
    string FullName,
    string Role,
    bool IsActive,
    DateTime CreatedAt
);
