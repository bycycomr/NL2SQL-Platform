using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Configuration;
using Microsoft.IdentityModel.Tokens;
using NL2SQL.CoreBackend.Application.Common.Interfaces;
using NL2SQL.CoreBackend.Domain.Entities;
using StackExchange.Redis;

namespace NL2SQL.CoreBackend.Infrastructure.Services;

public class JwtTokenService : IJwtTokenService
{
    private readonly IConfiguration _configuration;
    private readonly IConnectionMultiplexer _redis;
    private static readonly TimeSpan RefreshTokenExpiry = TimeSpan.FromDays(7);

    public JwtTokenService(IConfiguration configuration, IConnectionMultiplexer redis)
    {
        _configuration = configuration;
        _redis = redis;
    }

    public string GenerateAccessToken(User user)
    {
        var jwtSection = _configuration.GetSection("Jwt");
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtSection["SecretKey"]!));
        var credentials = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, user.Id.ToString()),
            new Claim(ClaimTypes.Email, user.Email),
            new Claim(ClaimTypes.Name, user.FullName),
            new Claim(ClaimTypes.Role, user.Role.ToString()),
        };

        var expireMinutes = int.Parse(jwtSection["ExpireMinutes"] ?? "15");

        var token = new JwtSecurityToken(
            issuer: jwtSection["Issuer"],
            audience: jwtSection["Audience"],
            claims: claims,
            expires: DateTime.UtcNow.AddMinutes(expireMinutes),
            signingCredentials: credentials
        );

        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    public string GenerateRefreshToken()
    {
        var bytes = new byte[64];
        using var rng = RandomNumberGenerator.Create();
        rng.GetBytes(bytes);
        return Convert.ToBase64String(bytes);
    }

    public async Task StoreRefreshTokenAsync(Guid userId, string refreshToken, CancellationToken ct = default)
    {
        var db = _redis.GetDatabase();
        var key = $"refresh_token:{refreshToken}";
        await db.StringSetAsync(key, userId.ToString(), RefreshTokenExpiry);
    }

    public async Task<Guid?> ValidateRefreshTokenAsync(string refreshToken, CancellationToken ct = default)
    {
        var db = _redis.GetDatabase();
        var key = $"refresh_token:{refreshToken}";
        var userId = await db.StringGetAsync(key);

        if (userId.IsNullOrEmpty)
            return null;

        return Guid.Parse(userId!);
    }

    public async Task RevokeRefreshTokenAsync(string refreshToken, CancellationToken ct = default)
    {
        var db = _redis.GetDatabase();
        var key = $"refresh_token:{refreshToken}";
        await db.KeyDeleteAsync(key);
    }
}
