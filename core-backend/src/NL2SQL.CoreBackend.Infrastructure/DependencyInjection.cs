using System.Text;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.Tokens;
using Polly;
using Polly.Extensions.Http;
using StackExchange.Redis;
using NL2SQL.CoreBackend.Application.Common.Interfaces;
using NL2SQL.CoreBackend.Infrastructure.Persistence;
using NL2SQL.CoreBackend.Infrastructure.Services;

namespace NL2SQL.CoreBackend.Infrastructure;

/// <summary>
/// Infrastructure katmanı servis kayıtları:
/// PostgreSQL (EF Core), Redis, JWT Auth, HttpClient
/// </summary>
public static class DependencyInjection
{
    public static IServiceCollection AddInfrastructureServices(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        // ─── PostgreSQL (EF Core) ───
        services.AddDbContext<AppDbContext>(options =>
            options.UseNpgsql(
                configuration.GetConnectionString("DefaultConnection"),
                npgsql =>
                {
                    npgsql.EnableRetryOnFailure(
                        maxRetryCount: 3,
                        maxRetryDelay: TimeSpan.FromSeconds(10),
                        errorCodesToAdd: null);
                    npgsql.CommandTimeout(30);
                })
            .UseSnakeCaseNamingConvention());

        // ─── Repository & UnitOfWork ───
        services.AddScoped(typeof(IRepository<>), typeof(EfRepository<>));
        services.AddScoped<IUnitOfWork, UnitOfWork>();

        // ─── Redis (Distributed Cache) ───
        services.AddStackExchangeRedisCache(options =>
        {
            options.Configuration = configuration.GetConnectionString("Redis");
            options.InstanceName = "nl2sql:";
        });

        // Doğrudan Redis erişimi (rate limiting vs. için)
        services.AddSingleton<IConnectionMultiplexer>(sp =>
            ConnectionMultiplexer.Connect(
                configuration.GetConnectionString("Redis")!));

        // ─── JWT Authentication ───
        var jwtSection = configuration.GetSection("Jwt");
        var secretKey = jwtSection["SecretKey"]!;

        services.AddAuthentication(options =>
        {
            options.DefaultAuthenticateScheme = JwtBearerDefaults.AuthenticationScheme;
            options.DefaultChallengeScheme = JwtBearerDefaults.AuthenticationScheme;
        })
        .AddJwtBearer(options =>
        {
            options.TokenValidationParameters = new TokenValidationParameters
            {
                ValidateIssuer = true,
                ValidateAudience = true,
                ValidateLifetime = true,
                ValidateIssuerSigningKey = true,
                ValidIssuer = jwtSection["Issuer"],
                ValidAudience = jwtSection["Audience"],
                IssuerSigningKey = new SymmetricSecurityKey(
                    Encoding.UTF8.GetBytes(secretKey)),
                ClockSkew = TimeSpan.FromMinutes(1)
            };
        });

        services.AddAuthorization();

        // ─── Auth Services ───
        services.AddScoped<IPasswordHasher, BcryptPasswordHasher>();
        services.AddScoped<IJwtTokenService, JwtTokenService>();

        // ─── HttpClient – AI Backend (Typed Client + Polly) ───
        services.AddHttpClient<IAIBackendService, AIBackendService>(client =>
        {
            client.BaseAddress = new Uri(
                configuration["AIBackend:BaseUrl"] ?? "http://ai-backend:8000");
            client.Timeout = TimeSpan.FromSeconds(120);
            client.DefaultRequestHeaders.Add("Accept", "application/json");
        })
        .AddPolicyHandler(GetRetryPolicy())
        .AddPolicyHandler(GetCircuitBreakerPolicy());

        return services;
    }

    /// <summary>
    /// 3 deneme, üstel geri çekilme (2s → 4s → 8s) + jitter
    /// </summary>
    private static IAsyncPolicy<HttpResponseMessage> GetRetryPolicy()
    {
        return HttpPolicyExtensions
            .HandleTransientHttpError()
            .WaitAndRetryAsync(
                retryCount: 3,
                sleepDurationProvider: attempt =>
                    TimeSpan.FromSeconds(Math.Pow(2, attempt))
                    + TimeSpan.FromMilliseconds(Random.Shared.Next(0, 500)),
                onRetry: (outcome, timespan, retryAttempt, _) =>
                {
                    // Polly retry loglama — Serilog pipeline'ından geçer
                });
    }

    /// <summary>
    /// 5 ardışık hata → 30 sn devre kesici
    /// </summary>
    private static IAsyncPolicy<HttpResponseMessage> GetCircuitBreakerPolicy()
    {
        return HttpPolicyExtensions
            .HandleTransientHttpError()
            .CircuitBreakerAsync(
                handledEventsAllowedBeforeBreaking: 5,
                durationOfBreak: TimeSpan.FromSeconds(30));
    }
}
