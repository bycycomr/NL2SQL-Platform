using MediatR;
using NL2SQL.CoreBackend.Application.Auth.DTOs;
using NL2SQL.CoreBackend.Application.Common.Interfaces;
using NL2SQL.CoreBackend.Application.Common.Models;
using NL2SQL.CoreBackend.Domain.Entities;
using NL2SQL.CoreBackend.Domain.Enums;

namespace NL2SQL.CoreBackend.Application.Auth.Commands;

public record RegisterCommand(RegisterRequest Request) : IRequest<ApiResponse<AuthResponse>>;

public class RegisterCommandHandler : IRequestHandler<RegisterCommand, ApiResponse<AuthResponse>>
{
    private readonly IUnitOfWork _unitOfWork;
    private readonly IPasswordHasher _passwordHasher;
    private readonly IJwtTokenService _jwtTokenService;

    public RegisterCommandHandler(
        IUnitOfWork unitOfWork,
        IPasswordHasher passwordHasher,
        IJwtTokenService jwtTokenService)
    {
        _unitOfWork = unitOfWork;
        _passwordHasher = passwordHasher;
        _jwtTokenService = jwtTokenService;
    }

    public async Task<ApiResponse<AuthResponse>> Handle(RegisterCommand command, CancellationToken ct)
    {
        var req = command.Request;

        var exists = await _unitOfWork.Users.AnyAsync(u => u.Email == req.Email, ct);
        if (exists)
            return ApiResponse<AuthResponse>.Fail("Bu e-posta adresi zaten kayıtlı.");

        var user = new User
        {
            Email = req.Email,
            PasswordHash = _passwordHasher.Hash(req.Password),
            FullName = req.FullName,
            Role = UserRole.Analyst
        };

        await _unitOfWork.Users.AddAsync(user, ct);
        await _unitOfWork.SaveChangesAsync(ct);

        var accessToken = _jwtTokenService.GenerateAccessToken(user);
        var refreshToken = _jwtTokenService.GenerateRefreshToken();
        await _jwtTokenService.StoreRefreshTokenAsync(user.Id, refreshToken, ct);

        var response = new AuthResponse(
            AccessToken: accessToken,
            RefreshToken: refreshToken,
            ExpiresAt: DateTime.UtcNow.AddMinutes(15),
            User: new UserDto(user.Id, user.Email, user.FullName, user.Role.ToString(), user.IsActive, user.CreatedAt)
        );

        return ApiResponse<AuthResponse>.Ok(response, "Kayıt başarılı.");
    }
}
