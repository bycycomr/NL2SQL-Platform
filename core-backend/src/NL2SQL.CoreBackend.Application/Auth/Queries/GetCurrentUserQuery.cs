using MediatR;
using NL2SQL.CoreBackend.Application.Auth.DTOs;
using NL2SQL.CoreBackend.Application.Common.Interfaces;
using NL2SQL.CoreBackend.Application.Common.Models;

namespace NL2SQL.CoreBackend.Application.Auth.Queries;

public record GetCurrentUserQuery(Guid UserId) : IRequest<ApiResponse<UserDto>>;

public class GetCurrentUserQueryHandler : IRequestHandler<GetCurrentUserQuery, ApiResponse<UserDto>>
{
    private readonly IUnitOfWork _unitOfWork;

    public GetCurrentUserQueryHandler(IUnitOfWork unitOfWork)
    {
        _unitOfWork = unitOfWork;
    }

    public async Task<ApiResponse<UserDto>> Handle(GetCurrentUserQuery query, CancellationToken ct)
    {
        var user = await _unitOfWork.Users.GetByIdAsync(query.UserId, ct);
        if (user is null)
            return ApiResponse<UserDto>.Fail("Kullanıcı bulunamadı.");

        var dto = new UserDto(user.Id, user.Email, user.FullName, user.Role.ToString(), user.IsActive, user.CreatedAt);
        return ApiResponse<UserDto>.Ok(dto);
    }
}
