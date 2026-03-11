using NL2SQL.CoreBackend.Domain.Entities;

namespace NL2SQL.CoreBackend.Application.Common.Interfaces;

public interface IJwtTokenService
{
    string GenerateAccessToken(User user);
    string GenerateRefreshToken();
    Task StoreRefreshTokenAsync(Guid userId, string refreshToken, CancellationToken ct = default);
    Task<Guid?> ValidateRefreshTokenAsync(string refreshToken, CancellationToken ct = default);
    Task RevokeRefreshTokenAsync(string refreshToken, CancellationToken ct = default);
}
