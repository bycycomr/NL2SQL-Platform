using MediatR;
using NL2SQL.CoreBackend.Application.Auth.DTOs;
using NL2SQL.CoreBackend.Application.Common.Interfaces;
using NL2SQL.CoreBackend.Application.Common.Models;

namespace NL2SQL.CoreBackend.Application.Auth.Commands;

public record RefreshTokenCommand(string RefreshToken) : IRequest<ApiResponse<AuthResponse>>;

public class RefreshTokenCommandHandler : IRequestHandler<RefreshTokenCommand, ApiResponse<AuthResponse>>
{
    private readonly IUnitOfWork _unitOfWork;
    private readonly IJwtTokenService _jwtTokenService;

    public RefreshTokenCommandHandler(IUnitOfWork unitOfWork, IJwtTokenService jwtTokenService)
    {
        _unitOfWork = unitOfWork;
        _jwtTokenService = jwtTokenService;
    }

    public async Task<ApiResponse<AuthResponse>> Handle(RefreshTokenCommand command, CancellationToken ct)
    {
        var userId = await _jwtTokenService.ValidateRefreshTokenAsync(command.RefreshToken, ct);
        if (userId is null)
            return ApiResponse<AuthResponse>.Fail("Geçersiz veya süresi dolmuş refresh token.");

        var user = await _unitOfWork.Users.GetByIdAsync(userId.Value, ct);
        if (user is null || !user.IsActive)
            return ApiResponse<AuthResponse>.Fail("Kullanıcı bulunamadı veya devre dışı.");

        await _jwtTokenService.RevokeRefreshTokenAsync(command.RefreshToken, ct);

        var newAccessToken = _jwtTokenService.GenerateAccessToken(user);
        var newRefreshToken = _jwtTokenService.GenerateRefreshToken();
        await _jwtTokenService.StoreRefreshTokenAsync(user.Id, newRefreshToken, ct);

        var response = new AuthResponse(
            AccessToken: newAccessToken,
            RefreshToken: newRefreshToken,
            ExpiresAt: DateTime.UtcNow.AddMinutes(15),
            User: new UserDto(user.Id, user.Email, user.FullName, user.Role.ToString(), user.IsActive, user.CreatedAt)
        );

        return ApiResponse<AuthResponse>.Ok(response, "Token yenilendi.");
    }
}
