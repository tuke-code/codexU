import Foundation

struct CodexNormalizedRateWindows: Equatable {
    let fiveHour: RateWindow?
    let sevenDay: RateWindow?
    let monthly: RateWindow?
    let unclassified: [RateWindow]
    let fiveHourMatchCount: Int
    let sevenDayMatchCount: Int
    let monthlyMatchCount: Int
}

enum CodexResetCreditNormalizer {
    static func normalizeAvailableCount(_ value: Int?) -> Int? {
        guard let value, value >= 0 else { return nil }
        return value
    }
}

enum CodexRateLimitNormalizer {
    static let fiveHourDurationMins = 300
    static let sevenDayDurationMins = 10_080
    /// Inclusive range covering calendar-month style windows (28–31 days).
    /// Team accounts currently report 43800 minutes (~30.4 days).
    static let monthlyMinDurationMins = 28 * 24 * 60
    static let monthlyMaxDurationMins = 31 * 24 * 60

    static func isMonthlyDuration(_ durationMins: Int?) -> Bool {
        guard let durationMins else { return false }
        return durationMins >= monthlyMinDurationMins && durationMins <= monthlyMaxDurationMins
    }

    static func isFiveHourDuration(_ durationMins: Int?) -> Bool {
        durationMins == fiveHourDurationMins
    }

    static func isSevenDayDuration(_ durationMins: Int?) -> Bool {
        durationMins == sevenDayDurationMins
    }

    static func normalize(_ windows: [RateWindow?]) -> CodexNormalizedRateWindows {
        let available = windows.compactMap { $0 }
        let fiveHourMatches = available.filter {
            isFiveHourDuration($0.windowDurationMins)
        }
        let sevenDayMatches = available.filter {
            isSevenDayDuration($0.windowDurationMins)
        }
        let monthlyMatches = available.filter {
            isMonthlyDuration($0.windowDurationMins)
        }
        let unclassified = available.filter { window in
            guard let duration = window.windowDurationMins else { return true }
            return !isFiveHourDuration(duration)
                && !isSevenDayDuration(duration)
                && !isMonthlyDuration(duration)
        }

        return CodexNormalizedRateWindows(
            fiveHour: fiveHourMatches.count == 1 ? fiveHourMatches[0] : nil,
            sevenDay: sevenDayMatches.count == 1 ? sevenDayMatches[0] : nil,
            monthly: monthlyMatches.count == 1 ? monthlyMatches[0] : nil,
            unclassified: unclassified,
            fiveHourMatchCount: fiveHourMatches.count,
            sevenDayMatchCount: sevenDayMatches.count,
            monthlyMatchCount: monthlyMatches.count
        )
    }

    static func isAuthoritative(
        hasWindowFields: Bool,
        hasMalformedWindow: Bool,
        normalized: CodexNormalizedRateWindows
    ) -> Bool {
        hasWindowFields
            && !hasMalformedWindow
            && normalized.fiveHourMatchCount <= 1
            && normalized.sevenDayMatchCount <= 1
            && normalized.monthlyMatchCount <= 1
            && normalized.unclassified.isEmpty
    }
}
