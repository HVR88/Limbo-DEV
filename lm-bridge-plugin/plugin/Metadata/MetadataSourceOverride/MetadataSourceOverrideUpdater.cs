using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NLog;
using NzbDrone.Common.Disk;
using NzbDrone.Common.Extensions;
using NzbDrone.Common.Http;
using NzbDrone.Common.Serializer;
using NzbDrone.Core.Configuration;
using NzbDrone.Core.Extras.Metadata;
using NzbDrone.Core.Lifecycle;
using NzbDrone.Core.MediaFiles;
using NzbDrone.Core.MediaFiles.Commands;
using NzbDrone.Core.Messaging.Commands;
using NzbDrone.Core.Messaging.Events;
using NzbDrone.Core.RootFolders;
using NzbDrone.Core.ThingiProvider;
using NzbDrone.Core.ThingiProvider.Events;

namespace LMBridgePlugin.Metadata.MetadataSourceOverride
{
    public class MetadataSourceOverrideUpdater :
        IHandle<ApplicationStartedEvent>,
        IHandle<ProviderAddedEvent<IMetadata>>,
        IHandle<ProviderUpdatedEvent<IMetadata>>,
        IHandle<ProviderDeletedEvent<IMetadata>>
    {
        private const string ImplementationName = nameof(MetadataSourceOverrideConsumer);
        private static string DisplayName => MetadataSourceOverrideConsumer.DisplayName;
        private const string AutoEnableMarkerFile = ".lmbridge.autoenable";

        private readonly IMetadataRepository _metadataRepository;
        private readonly IConfigService _configService;
        private readonly IDiskProvider _diskProvider;
        private readonly IHttpClient _httpClient;
        private readonly IManageCommandQueue _commandQueueManager;
        private readonly IRootFolderService _rootFolderService;
        private readonly Logger _logger;
        private readonly string _autoEnableMarkerPath;
        private string? _lastReleaseFilterPayload;

        public MetadataSourceOverrideUpdater(IMetadataRepository metadataRepository,
                                             IConfigService configService,
                                             IDiskProvider diskProvider,
                                             IHttpClient httpClient,
                                             IManageCommandQueue commandQueueManager,
                                             IRootFolderService rootFolderService,
                                             Logger logger)
        {
            _metadataRepository = metadataRepository;
            _configService = configService;
            _diskProvider = diskProvider;
            _httpClient = httpClient;
            _commandQueueManager = commandQueueManager;
            _rootFolderService = rootFolderService;
            _logger = logger;
            _autoEnableMarkerPath = ResolveAutoEnableMarkerPath();
        }

        public void Handle(ApplicationStartedEvent message)
        {
            ApplyFromRepository(logEvenIfUnchanged: true);
        }

        public void Handle(ProviderAddedEvent<IMetadata> message)
        {
            ApplyDefinition(message.Definition);
        }

        public void Handle(ProviderUpdatedEvent<IMetadata> message)
        {
            ApplyDefinition(message.Definition);
        }

        public void Handle(ProviderDeletedEvent<IMetadata> message)
        {
            ApplyFromRepository();
        }

        private void ApplyFromRepository(bool logEvenIfUnchanged = false)
        {
            var definitions = _metadataRepository.All()
                .Where(d => d.Implementation == ImplementationName)
                .ToList();

            if (definitions.Count == 0)
            {
                if (_configService.MetadataSource.IsNotNullOrWhiteSpace())
                {
                    _logger.Info("Clearing MetadataSource override (provider removed).");
                    _configService.MetadataSource = string.Empty;
                }

                return;
            }

            foreach (var definition in definitions)
            {
                EnsureDisplayName(definition);
                EnsureDefaultUrl(definition);
                EnsureDefaultEnabled(definition);
            }

            var enabled = definitions.FirstOrDefault(d => d.Enable);
            if (enabled != null)
            {
                ApplyDefinition(enabled, logEvenIfUnchanged);
                return;
            }

            // No enabled definitions; clear if current matches any configured URL.
            var configuredUrls = definitions
                .Select(d => (d.Settings as MetadataSourceOverrideSettings)?.MetadataSource)
                .Select(s => (s ?? string.Empty).Trim())
                .Where(s => s.Length > 0)
                .ToList();

            if (configuredUrls.Contains(_configService.MetadataSource))
            {
                _logger.Info("Clearing MetadataSource override (provider disabled).");
                _configService.MetadataSource = string.Empty;
            }
        }

        private void ApplyDefinition(ProviderDefinition definition, bool logEvenIfUnchanged = false)
        {
            if (definition?.Implementation != ImplementationName)
            {
                return;
            }

            var settings = definition.Settings as MetadataSourceOverrideSettings;
            if (settings == null)
            {
                return;
            }

            EnsureDisplayName(definition);
            EnsureDefaultUrl(definition);
            EnsureDefaultEnabled(definition);

            var url = settings.MetadataSource?.Trim();
            var canApply = definition.Enable && url.IsNotNullOrWhiteSpace();

            if (canApply)
            {
                if (!string.Equals(_configService.MetadataSource, url, StringComparison.OrdinalIgnoreCase))
                {
                    _logger.Info("Applying MetadataSource override: {0}", url);
                    _configService.MetadataSource = url;
                }
                else if (logEvenIfUnchanged)
                {
                    _logger.Info("MetadataSource override already set: {0}", url);
                }
            }
            else if (string.Equals(_configService.MetadataSource, url, StringComparison.OrdinalIgnoreCase))
            {
                _logger.Info("Clearing MetadataSource override (provider disabled).");
                _configService.MetadataSource = string.Empty;
            }

            SyncReleaseFilterConfig(definition, settings, logEvenIfUnchanged);
            HandleForceRescan(definition, settings);
        }

        private void HandleForceRescan(ProviderDefinition definition, MetadataSourceOverrideSettings settings)
        {
            if (definition == null || settings == null)
            {
                return;
            }

            if (!definition.Enable || !settings.ForceRescanReleases)
            {
                return;
            }

            if (definition is not MetadataDefinition metadataDefinition)
            {
                return;
            }

            try
            {
                var folders = _rootFolderService.All()
                    .Select(folder => folder.Path)
                    .Where(path => path.IsNotNullOrWhiteSpace())
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .ToList();

                if (folders.Count == 0)
                {
                    _logger.Warn("Force Rescan requested but no root folders were found.");
                    return;
                }

                _commandQueueManager.Push(new RescanFoldersCommand(folders, FilterFilesType.Known, false, null),
                    trigger: CommandTrigger.Manual);
                _logger.Info("Queued rescan of releases for {0} root folder(s).", folders.Count);
            }
            finally
            {
                settings.ForceRescanReleases = false;
                _metadataRepository.Update(metadataDefinition);
                _logger.Info("Cleared Force Rescan of Releases flag.");
            }
        }

        private void EnsureDisplayName(ProviderDefinition definition)
        {
            if (definition == null)
            {
                return;
            }

            if (!string.Equals(definition.Name, DisplayName, StringComparison.Ordinal))
            {
                if (definition is not MetadataDefinition metadataDefinition)
                {
                    return;
                }

                metadataDefinition.Name = DisplayName;
                _metadataRepository.Update(metadataDefinition);
                _logger.Info("Updated metadata provider display name to: {0}", DisplayName);
            }
        }

        private void EnsureDefaultUrl(ProviderDefinition definition)
        {
            if (definition is not MetadataDefinition metadataDefinition)
            {
                return;
            }

            if (metadataDefinition.Settings is not MetadataSourceOverrideSettings settings)
            {
                return;
            }

            if (settings.MetadataSource.IsNullOrWhiteSpace())
            {
                settings.MetadataSource = MetadataSourceOverrideSettings.DefaultMetadataSource;
                _metadataRepository.Update(metadataDefinition);
                _logger.Info("Defaulted MetadataSource to: {0}", settings.MetadataSource);
            }
        }

        private void EnsureDefaultEnabled(ProviderDefinition definition)
        {
            if (definition is not MetadataDefinition metadataDefinition)
            {
                return;
            }

            if (metadataDefinition.Settings is not MetadataSourceOverrideSettings settings)
            {
                return;
            }

            if (metadataDefinition.Enable)
            {
                MarkAutoEnableAppliedIfNeeded();

                return;
            }

            if (IsAutoEnableApplied())
            {
                return;
            }

            var url = settings.MetadataSource?.Trim();
            if (url.IsNullOrWhiteSpace() ||
                string.Equals(url, MetadataSourceOverrideSettings.DefaultMetadataSource, StringComparison.OrdinalIgnoreCase))
            {
                metadataDefinition.Enable = true;
                MarkAutoEnableAppliedIfNeeded();
                _metadataRepository.Update(metadataDefinition);
                _logger.Info("Enabled metadata provider by default.");
            }
        }

        private void SyncReleaseFilterConfig(ProviderDefinition definition, MetadataSourceOverrideSettings settings, bool logEvenIfUnchanged)
        {
            if (definition == null || settings == null)
            {
                return;
            }

            var baseUrl = settings.MetadataSource?.Trim();
            if (string.IsNullOrWhiteSpace(baseUrl))
            {
                return;
            }

            var url = baseUrl.TrimEnd('/') + "/config/release-filter";
            var excludeTokens = NormalizeTokens(settings.ExcludeMediaFormats);
            var includeTokens = NormalizeTokens(settings.KeepOnlyFormats);
            if (includeTokens.Length > 0)
            {
                excludeTokens = Array.Empty<string>();
            }
            var keepOnlyMediaCount = Math.Clamp(settings.KeepOnlyMediaCount.GetValueOrDefault(), 0, 999);
            var prefer = settings.Prefer == (int)MediaPreferOption.Analog ? "analog" : "digital";
            var payload = new ReleaseFilterPayload
            {
                Enabled = definition.Enable,
                ExcludeMediaFormats = definition.Enable ? excludeTokens : Array.Empty<string>(),
                IncludeMediaFormats = definition.Enable ? includeTokens : Array.Empty<string>(),
                KeepOnlyMediaCount = definition.Enable && keepOnlyMediaCount > 0 ? keepOnlyMediaCount : null,
                Prefer = definition.Enable && keepOnlyMediaCount > 0 ? prefer : null
            };

            var json = payload.ToJson();
            if (!logEvenIfUnchanged && string.Equals(_lastReleaseFilterPayload, json, StringComparison.Ordinal))
            {
                return;
            }

            try
            {
                var requestBuilder = new HttpRequestBuilder(url).Post();
                var request = requestBuilder.Build();
                request.Headers.ContentType = "application/json";
                request.SetContent(json);
                _httpClient.Post(request);
                _lastReleaseFilterPayload = json;
            }
            catch (Exception ex)
            {
                _logger.Warn(ex, "Failed to sync release filter config to LM-Bridge.");
            }
        }

        private static string[] NormalizeTokens(IEnumerable<string> values)
        {
            if (values == null)
            {
                return Array.Empty<string>();
            }

            return values
                .Select(value => value?.Trim())
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => value!.ToLowerInvariant())
                .Distinct()
                .ToArray();
        }

        private class ReleaseFilterPayload
        {
            public bool Enabled { get; set; }
            public IEnumerable<string> ExcludeMediaFormats { get; set; } = Array.Empty<string>();
            public IEnumerable<string> IncludeMediaFormats { get; set; } = Array.Empty<string>();
            public int? KeepOnlyMediaCount { get; set; }
            public string? Prefer { get; set; }
        }

        private string ResolveAutoEnableMarkerPath()
        {
            var assemblyPath = typeof(MetadataSourceOverrideUpdater).Assembly.Location;
            var baseDir = !string.IsNullOrWhiteSpace(assemblyPath)
                ? Path.GetDirectoryName(assemblyPath)
                : null;
            baseDir ??= AppContext.BaseDirectory;
            if (string.IsNullOrWhiteSpace(baseDir))
            {
                baseDir = AppContext.BaseDirectory;
            }

            return Path.Combine(baseDir, AutoEnableMarkerFile);
        }

        private bool IsAutoEnableApplied()
        {
            return _diskProvider.FileExists(_autoEnableMarkerPath);
        }

        private void MarkAutoEnableAppliedIfNeeded()
        {
            if (IsAutoEnableApplied())
            {
                return;
            }

            try
            {
                var folder = Path.GetDirectoryName(_autoEnableMarkerPath);
                if (folder.IsNotNullOrWhiteSpace())
                {
                    _diskProvider.EnsureFolder(folder);
                }

                _diskProvider.WriteAllText(_autoEnableMarkerPath, DateTime.UtcNow.ToString("O"));
            }
            catch (Exception ex)
            {
                _logger.Warn(ex, "Failed to persist auto-enable marker.");
            }
        }
    }
}
