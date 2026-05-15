FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY api/TimelineForChatGPT.HealthApi.csproj api/
RUN dotnet restore api/TimelineForChatGPT.HealthApi.csproj
COPY api/ api/
RUN dotnet publish api/TimelineForChatGPT.HealthApi.csproj -c Release -o /app/publish --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "TimelineForChatGPT.HealthApi.dll"]
