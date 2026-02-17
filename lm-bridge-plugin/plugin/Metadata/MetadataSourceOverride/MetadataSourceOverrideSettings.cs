using System;
using System.Collections.Generic;
using System.Linq;
using FluentValidation;
using FluentValidation.Results;
using FluentValidation.Validators;
using NzbDrone.Core.Annotations;
using NzbDrone.Core.Extras.Metadata;
using NzbDrone.Core.ThingiProvider;
using NzbDrone.Core.Validation;

namespace LMBridgePlugin.Metadata.MetadataSourceOverride
{
    public class MetadataSourceOverrideSettingsValidator : AbstractValidator<MetadataSourceOverrideSettings>
    {
        public MetadataSourceOverrideSettingsValidator()
        {
            RuleFor(x => x.MetadataSource)
                .NotEmpty()
                .WithMessage("Metadata Source URL is required.")
                .IsValidUrl()
                .WithMessage("Metadata Source must be a valid HTTP or HTTPS URL.");

            RuleFor(x => x).Custom((settings, context) =>
            {
                var hasExclude = settings.ExcludeMediaFormats?.Any(v => !string.IsNullOrWhiteSpace(v)) == true;
                var hasInclude = settings.KeepOnlyFormats?.Any(v => !string.IsNullOrWhiteSpace(v)) == true;

                if (hasExclude && hasInclude)
                {
                    const string message = "Use either Exclude Media Formats or Keep only formats, not both.";
                    context.AddFailure(nameof(MetadataSourceOverrideSettings.ExcludeMediaFormats), message);
                    context.AddFailure(nameof(MetadataSourceOverrideSettings.KeepOnlyFormats), message);
                }
            });

            RuleFor(x => x.KeepOnlyMediaCount)
                .GreaterThan(0)
                .When(x => x.KeepOnlyMediaCount.HasValue)
                .WithMessage("Keep only # media must be greater than 0.");

            RuleFor(x => x.ExcludeMediaFormats)
                .Custom((values, context) =>
                {
                    AddUnknownFormatWarnings(values, nameof(MetadataSourceOverrideSettings.ExcludeMediaFormats), context);
                });

            RuleFor(x => x.KeepOnlyFormats)
                .Custom((values, context) =>
                {
                    AddUnknownFormatWarnings(values, nameof(MetadataSourceOverrideSettings.KeepOnlyFormats), context);
                });
        }

        private static void AddUnknownFormatWarnings(IEnumerable<string> values, string propertyName, CustomContext context)
        {
            if (values == null)
            {
                return;
            }

            var unknown = values
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => value.Trim())
                .Where(value => !IsKnownFormatToken(value))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToList();

            if (unknown.Count == 0)
            {
                return;
            }

            var message = $"Unrecognized format token(s): {string.Join(", ", unknown)}. See the link for supported names.";
            var failure = new ValidationFailure(propertyName, message)
            {
                CustomState = NzbDroneValidationState.Warning
            };
            context.AddFailure(failure);
        }

        private static bool IsKnownFormatToken(string token)
        {
            if (string.IsNullOrWhiteSpace(token))
            {
                return true;
            }

            if (MediaFormats.MetaFormatNamesSet.Contains(token))
            {
                return true;
            }

            var normalized = token.Trim().ToLowerInvariant();
            foreach (var format in MediaFormats.FormatNamesLower)
            {
                if (format.Contains(normalized, StringComparison.Ordinal))
                {
                    return true;
                }
            }

            return false;
        }
    }

    public class MetadataSourceOverrideSettings : IProviderConfig
    {
        private static readonly MetadataSourceOverrideSettingsValidator Validator = new();

        public const string DefaultMetadataSource = "http://127.0.0.1:5001";

        [FieldDefinition(0, Label = "API URL", Type = FieldType.Url, Placeholder = DefaultMetadataSource, Section = MetadataSectionType.Metadata, HelpText = "HTTP://ADDRESS:PORT of your LM Bridge Instance")]
        public string MetadataSource { get; set; } = DefaultMetadataSource;

        [FieldDefinition(1, Label = "Exclude Media Formats", HelpText = "List of formats to remove from releases: vinyl, cassette, CD-R, etc. Special aliases: analog / digital", HelpLink = "https://github.com/HVR88/LM-Bridge", Type = FieldType.Tag, Section = MetadataSectionType.Metadata)]
        public IEnumerable<string> ExcludeMediaFormats { get; set; } = Array.Empty<string>();

        [FieldDefinition(2, Label = "Keep only formats", HelpText = "Only show these media formats for releases", HelpLink = "https://github.com/HVR88/LM-Bridge", Type = FieldType.Tag, Section = MetadataSectionType.Metadata)]
        public IEnumerable<string> KeepOnlyFormats { get; set; } = Array.Empty<string>();

        [FieldDefinition(3, Label = "Keep only # media", HelpText = "Only keep and show a maximim number of media issues per release", Type = FieldType.Number, Section = MetadataSectionType.Metadata)]
        public int? KeepOnlyMediaCount { get; set; }

        [FieldDefinition(4, Label = "Prefer", HelpText = "when limiting media issues, prefer digital or analog formats?", HelpLink = "https://github.com/HVR88/LM-Bridge", Type = FieldType.Select, SelectOptions = typeof(MediaPreferOption), Section = MetadataSectionType.Metadata)]
        public int Prefer { get; set; } = (int)MediaPreferOption.Digital;

        public bool UseAtOwnRisk { get; set; } = true;

        public NzbDroneValidationResult Validate() => new(Validator.Validate(this));
    }

    public enum MediaPreferOption
    {
        [FieldOption("Digital")]
        Digital = 0,
        [FieldOption("Analog")]
        Analog = 1
    }
}
