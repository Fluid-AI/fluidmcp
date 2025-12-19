// Props for a single Airbnb listing card.
// We define only the fields that the UI actually uses.
// This keeps the component simple and type-safe.
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
    // Utility function to fix encoding issue coming from API
    // (₹ symbol sometimes appears as â‚¹)
    function fixCurrency(text?: string) {
        if (!text) return "";
        return text.replace(/â‚¹/g, "₹");
    }

    // Extract listing name safely using optional chaining
    const name =
        item?.demandStayListing?.description?.name
        ?.localizedStringWithTranslationPreference;

    // Extract price label (already formatted by Airbnb)    
    const price =
        item?.structuredDisplayPrice?.primaryLine?.accessibilityLabel;

    return (
        <div className="card">
            {/* Listing title */}
            <h4>{name}</h4>

            {/* Bedroom / bed info */}
            {item.structuredContent?.primaryLine && (
                <p>{item.structuredContent.primaryLine}</p>
            )}

            {/* Average rating (if available)*/}
            {item.avgRatingA11yLabel && (
                <p>⭐ {item.avgRatingA11yLabel}</p>
            )}

            {/* Price info */}
            {price && <p>{fixCurrency(price)}</p>}
            
            {/* External Airbnb link */}
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