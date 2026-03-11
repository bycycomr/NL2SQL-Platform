namespace NL2SQL.CoreBackend.Application.Auth.DTOs;

public record LoginRequest(
    string Email,
    string Password
);
