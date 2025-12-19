type Props = {
    item: {
        id: string;
        url: string;
        avgRatingA11yLabel?: string;
        structuredContent?: {
        primaryLine?: string;
        };
        structuredDisplayPrice?: {
        primaryLine?: {
            accessibilityLabel?: string;
        };
        };
        demandStayListing?: {
        description?: {
            name?: {
            localizedStringWithTranslationPreference?: string;
            };
        };
        };
    };
};

export default function ListingCard({ item }: Props) {
    function fixCurrency(text?: string) {
        if (!text) return "";
        return text.replace(/â‚¹/g, "₹");
    }

    const name =
        item?.demandStayListing?.description?.name
        ?.localizedStringWithTranslationPreference;

    const price =
        item?.structuredDisplayPrice?.primaryLine?.accessibilityLabel;

    return (
        <div className="card">
        <h4>{name}</h4>

        {item.structuredContent?.primaryLine && (
            <p>{item.structuredContent.primaryLine}</p>
        )}

        {item.avgRatingA11yLabel && (
            <p>⭐ {item.avgRatingA11yLabel}</p>
        )}

        {price && <p>{fixCurrency(price)}</p>}

        <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
        >
            View on Airbnb
        </a>
        </div>
    );
}