using MediatR;
using NL2SQL.CoreBackend.Application.Auth.DTOs;
using NL2SQL.CoreBackend.Application.Common.Interfaces;
using NL2SQL.CoreBackend.Application.Common.Models;

namespace NL2SQL.CoreBackend.Application.Auth.Commands;

public record LoginCommand(LoginRequest Request) : IRequest<ApiResponse<AuthResponse>>;

public class LoginCommandHandler : IRequestHandler<LoginCommand, ApiResponse<AuthResponse>>
{
    private readonly IUnitOfWork _unitOfWork;
    private readonly IPasswordHasher _passwordHasher;
    private readonly IJwtTokenService _jwtTokenService;

    public LoginCommandHandler(
        IUnitOfWork unitOfWork,
        IPasswordHasher passwordHasher,
        IJwtTokenService jwtTokenService)
    {
        _unitOfWork = unitOfWork;
        _passwordHasher = passwordHasher;
        _jwtTokenService = jwtTokenService;
    }

    public async Task<ApiResponse<AuthResponse>> Handle(LoginCommand command, CancellationToken ct)
    {
        var req = command.Request;

        var users = await _unitOfWork.Users.FindAsync(u => u.Email == req.Email, ct);
        var user = users.FirstOrDefault();

        if (user is null || !_passwordHasher.Verify(req.Password, user.PasswordHash))
            return ApiResponse<AuthResponse>.Fail("E-posta veya şifre hatalı.");

        if (!user.IsActive)
            return ApiResponse<AuthResponse>.Fail("Hesabınız devre dışı bırakılmış.");

        var accessToken = _jwtTokenService.GenerateAccessToken(user);
        var refreshToken = _jwtTokenService.GenerateRefreshToken();
        await _jwtTokenService.StoreRefreshTokenAsync(user.Id, refreshToken, ct);

        var response = new AuthResponse(
            AccessToken: accessToken,
            RefreshToken: refreshToken,
            ExpiresAt: DateTime.UtcNow.AddMinutes(15),
            User: new UserDto(user.Id, user.Email, user.FullName, user.Role.ToString(), user.IsActive, user.CreatedAt)
        );

        return ApiResponse<AuthResponse>.Ok(response, "Giriş başarılı.");
    }
}
