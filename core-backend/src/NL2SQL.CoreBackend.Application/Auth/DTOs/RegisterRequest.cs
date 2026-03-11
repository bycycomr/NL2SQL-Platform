namespace NL2SQL.CoreBackend.Application.Auth.DTOs;

public record RegisterRequest(
    string Email,
    string Password,
    string FullName
);
