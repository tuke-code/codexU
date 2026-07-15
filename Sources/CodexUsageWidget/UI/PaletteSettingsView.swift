import SwiftUI

struct PaletteSettingsView: View {
    @ObservedObject var settings: AppSettings
    let onOpenLibrary: () -> Void
    @Environment(\.colorScheme) private var colorScheme

    private var selectedDescriptor: PaletteDescriptor? {
        settings.paletteCatalog
            .descriptors(language: settings.language == .zh ? "zh-Hans" : "en")
            .first { $0.id == settings.paletteID }
    }

    var body: some View {
        VStack(alignment: .trailing, spacing: 5) {
            if let descriptor = selectedDescriptor {
                currentPaletteButton(descriptor)
            }
            if let notice = settings.paletteFallbackNotice {
                Text(settings.language.text("配色不可用，已恢复默认", "Palette unavailable; restored to default"))
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(FixedVisualPalette.statusWarning)
                    .help(notice.unavailableID)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(settings.language.text("配色", "Color palette"))
    }

    private func currentPaletteButton(_ descriptor: PaletteDescriptor) -> some View {
        let tokens = settings.paletteCatalog.resolve(id: descriptor.id, appearance: PaletteAppearance(colorScheme))
        return Button(action: onOpenLibrary) {
            HStack(spacing: 9) {
                PaletteSwatches(tokens: tokens, diameter: 10)
                VStack(alignment: .leading, spacing: 2) {
                    Text(descriptor.displayName)
                        .font(.system(size: 10.5, weight: .semibold))
                        .foregroundStyle(Color.primary)
                        .lineLimit(1)
                    Text(settings.language.text("查看与选择配色", "Browse and choose palettes"))
                        .font(.system(size: 8.5, weight: .medium))
                        .foregroundStyle(Color.secondary)
                }
                Spacer(minLength: 4)
                Image(systemName: "chevron.right")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(Color.secondary)
            }
            .padding(.horizontal, 10)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .fill(FixedVisualPalette.controlFill(colorScheme))
                    .overlay(
                        RoundedRectangle(cornerRadius: 9, style: .continuous)
                            .strokeBorder(tokens.selection.stroke.color, lineWidth: 1)
                    )
            )
        }
        .buttonStyle(.plain)
        .help(descriptor.shortDescription)
        .accessibilityLabel(settings.language.text("当前配色：\(descriptor.displayName)，打开配色库", "Current palette: \(descriptor.displayName). Open palette library"))
    }
}

struct PaletteLibraryView: View {
    @ObservedObject var settings: AppSettings
    @Environment(\.colorScheme) private var colorScheme

    private var descriptors: [PaletteDescriptor] {
        settings.paletteCatalog.descriptors(language: settings.language == .zh ? "zh-Hans" : "en")
    }

    private let columns = [
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12)
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 4) {
                Text(settings.language.text("精选配色", "Curated Palettes"))
                    .font(.system(size: 22, weight: .bold))
                Text(settings.language.text(
                    "每套配色均同时适配浅色与深色外观，选择后立即应用。",
                    "Every palette supports both Light and Dark appearances and applies immediately."
                ))
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(Color.secondary)
            }
            .padding(.horizontal, 20)
            .padding(.top, 18)
            .padding(.bottom, 14)

            Divider().opacity(0.55)

            ScrollView(.vertical, showsIndicators: true) {
                LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
                    ForEach(descriptors) { descriptor in
                        PaletteLibraryCard(
                            descriptor: descriptor,
                            catalog: settings.paletteCatalog,
                            language: settings.language,
                            selected: descriptor.id == settings.paletteID
                        ) {
                            settings.selectPalette(descriptor.id)
                        }
                    }
                }
                .padding(16)
            }

            Divider().opacity(0.55)

            HStack {
                Text(settings.language.text("当前：", "Current: "))
                    .foregroundStyle(Color.secondary)
                Text(descriptors.first(where: { $0.id == settings.paletteID })?.displayName ?? settings.paletteID)
                    .fontWeight(.semibold)
                Spacer()
                Button(settings.language.text("恢复默认配色", "Restore Default Palette")) {
                    settings.resetPalette()
                }
                .buttonStyle(.borderless)
                .disabled(settings.paletteID == PaletteCatalog.defaultPaletteID)
            }
            .font(.system(size: 10.5, weight: .medium))
            .padding(.horizontal, 20)
            .frame(height: 46)
        }
        .frame(minWidth: 600, minHeight: 540)
        .background(FixedVisualPalette.sectionFill(colorScheme).opacity(0.35))
        .appVisualEnvironment(
            catalog: settings.paletteCatalog,
            paletteID: settings.paletteID,
            appearance: PaletteAppearance(colorScheme)
        )
        .readableForegroundHierarchy(colorScheme)
    }
}

private struct PaletteLibraryCard: View {
    let descriptor: PaletteDescriptor
    let catalog: PaletteCatalog
    let language: WidgetLanguage
    let selected: Bool
    let onSelect: () -> Void

    private var lightTokens: ResolvedVisualTokens { catalog.resolve(id: descriptor.id, appearance: .light) }
    private var darkTokens: ResolvedVisualTokens { catalog.resolve(id: descriptor.id, appearance: .dark) }

    var body: some View {
        Button(action: onSelect) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .top, spacing: 8) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(descriptor.displayName)
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(Color.primary)
                        Text(descriptor.shortDescription)
                            .font(.system(size: 9.5, weight: .medium))
                            .foregroundStyle(Color.secondary)
                            .lineLimit(2)
                    }
                    Spacer(minLength: 4)
                    Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(selected ? lightTokens.selection.foreground.color : Color.secondary.opacity(0.55))
                }

                HStack(spacing: 8) {
                    PaletteAppearancePreview(
                        title: language.text("浅色", "Light"),
                        tokens: lightTokens,
                        background: Color.white.opacity(0.92),
                        foreground: Color.black.opacity(0.72)
                    )
                    PaletteAppearancePreview(
                        title: language.text("深色", "Dark"),
                        tokens: darkTokens,
                        background: Color(red: 0.09, green: 0.10, blue: 0.12),
                        foreground: Color.white.opacity(0.82)
                    )
                }

                Text(descriptor.inspirationNote)
                    .font(.system(size: 8.5, weight: .medium))
                    .foregroundStyle(Color.secondary)
                    .lineLimit(2)
                    .frame(minHeight: 21, alignment: .topLeading)
            }
            .padding(12)
            .frame(maxWidth: .infinity, minHeight: 174, alignment: .topLeading)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(selected ? lightTokens.selection.fill.color : FixedVisualPalette.controlFill(.light).opacity(0.55))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .strokeBorder(
                                selected ? lightTokens.selection.stroke.color : Color.secondary.opacity(0.2),
                                lineWidth: selected ? 1.4 : 0.8
                            )
                    )
            )
        }
        .buttonStyle(.plain)
        .help(descriptor.shortDescription)
        .accessibilityLabel(descriptor.displayName)
        .accessibilityValue(selected ? language.text("已选择", "Selected") : "")
    }
}

private struct PaletteAppearancePreview: View {
    let title: String
    let tokens: ResolvedVisualTokens
    let background: Color
    let foreground: Color

    var body: some View {
        HStack(spacing: 8) {
            ZStack {
                QuotaRingSegment(
                    percent: 88,
                    tokens: tokens.quota.primary,
                    ringAsset: tokens.assets[.quotaRingPrimary],
                    capAsset: tokens.assets[.quotaCapPrimary],
                    lineWidth: 6
                )
                QuotaRingSegment(
                    percent: 66,
                    tokens: tokens.quota.secondary,
                    ringAsset: tokens.assets[.quotaRingSecondary],
                    capAsset: tokens.assets[.quotaCapSecondary],
                    lineWidth: 4
                )
                .frame(width: 28, height: 28)
            }
            .frame(width: 40, height: 40)

            VStack(alignment: .leading, spacing: 5) {
                Text(title)
                    .font(.system(size: 8.5, weight: .semibold))
                    .foregroundStyle(foreground)
                PaletteSwatches(tokens: tokens, diameter: 7)
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .fill(LinearGradient(
                        colors: tokens.data.valueProgress.map(\.color),
                        startPoint: .leading,
                        endPoint: .trailing
                    ))
                    .frame(height: 4)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 7)
        .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(background))
    }
}

private struct PaletteSwatches: View {
    let tokens: ResolvedVisualTokens
    let diameter: CGFloat

    var body: some View {
        HStack(spacing: max(2, diameter * 0.32)) {
            ForEach(Array(swatchColors.enumerated()), id: \.offset) { _, color in
                Circle().fill(color.color).frame(width: diameter, height: diameter)
            }
        }
    }

    private var swatchColors: [PaletteColor] {
        [tokens.quota.primary.start, tokens.quota.primary.end, tokens.quota.secondary.end, tokens.data.series[2]]
    }
}
