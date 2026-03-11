using MediatR;
using NL2SQL.CoreBackend.Application.Common.Interfaces;
using NL2SQL.CoreBackend.Application.Common.Models;

namespace NL2SQL.CoreBackend.Application.Auth.Commands;

public record LogoutCommand(string RefreshToken) : IRequest<ApiResponse<bool>>;

public class LogoutCommandHandler : IRequestHandler<LogoutCommand, ApiResponse<bool>>
{
    private readonly IJwtTokenService _jwtTokenService;

    public LogoutCommandHandler(IJwtTokenService jwtTokenService)
    {
        _jwtTokenService = jwtTokenService;
    }

    public async Task<ApiResponse<bool>> Handle(LogoutCommand command, CancellationToken ct)
    {
        await _jwtTokenService.RevokeRefreshTokenAsync(command.RefreshToken, ct);
        return ApiResponse<bool>.Ok(true, "Çıkış başarılı.");
    }
}
