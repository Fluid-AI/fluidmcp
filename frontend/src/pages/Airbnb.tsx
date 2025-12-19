import { useState } from "react";
import { callAirbnbSearch } from "../services/api";
import ListingCard from "../components/ListingCard";

/* Minimal type definition for an Airbnb listing.
 We only include fields that are actually used in the UI.
*/
type AirbnbListing = {
  id: string;
  url: string;
  badges?: string;
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



export default function Airbnb(){
    /* ---------------------- Form states ---------------------- */
    const [location, setLocation] =  useState("");
    const [adults, setAdults] = useState(1);
    const [checkin, setCheckin] = useState("");
    const [checkout, setCheckout] = useState("");

    /* ---------------------- UI state ------------------------ */
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    /* ---------------------- Results state ------------------- */
    const [results, setResults] = useState<AirbnbListing[]>([]);
    const [searchUrl, setSearchUrl] = useState<string | null>(null);

    /* ---------------------- Pagination state ---------------- */
    const [nextCursor, setNextCursor] = useState<string | null>(null);
    const [loadingMore, setLoadingMore] = useState(false);

    /*Handles the initial Airbnb search.
    Builds the MCP payload and sends it to the backend.
    */
    const handleSearch = async () => {
        if (!location || !checkin || !checkout) {
            alert("Please fill all fields");
            return;
        }
        const payload = {
            name : "airbnb_search",
            arguments : {
                location,
                adults,
                checkin,
                checkout,
            },
        };
        try{
            setLoading(true);
            setError(null);
            // console.log("Load payload:", payload); for debugging
            const data = await callAirbnbSearch(payload);
            // Parse MCP response into usable UI data
            const { listings, searchUrl } = parseAirbnbResults(data);
            setResults(listings);
            setSearchUrl(searchUrl)
        }catch (err){
            setError("Something went wrong while fetching results");
        }finally{
            setLoading(false);
        }
    };

    /* Parses the MCP response format.
    MCP returns text content containing a JSON string.
    */
    function parseAirbnbResults(raw: any) :
    { listings: AirbnbListing[]; searchUrl: string | null } {
        const textBlock = raw?.result?.content?.[0]?.text;
        if (!textBlock) return { listings: [], searchUrl: null };

        const parsed = JSON.parse(textBlock);
        // Save cursor for pagination
        setNextCursor(parsed.paginationInfo?.nextPageCursor ?? null);

        return {
            listings: (parsed.searchResults || []) as AirbnbListing[],
            searchUrl: parsed.searchUrl || null,
        };
    }
    
    /* Loads the next page of results using cursor-based pagination.
    Also removes duplicate listings using the listing ID.
    */
    const handleLoadMore = async ()=>{
        if(!nextCursor) return;
        const payload = {
            name : "airbnb_search",
            arguments : {
                location,
                adults,
                checkin,
                checkout,
                cursor: nextCursor,
            },
        };

        try{
            setLoadingMore(true);
            const data = await callAirbnbSearch(payload);
            const textBlock = data?.result?.content?.[0]?.text;
            if(!textBlock) return;

            // console.log("Load more payload:", payload); for debugging
            const parsed =JSON.parse(textBlock);

            // Merge new results while preventing duplicates
            setResults((prev: AirbnbListing[]) => {
                const seen = new Set(prev.map((item: AirbnbListing) => item.id));
                
                const newItems = (parsed.searchResults as AirbnbListing[]).filter(
                    (item: AirbnbListing) => !seen.has(item.id));

                return [...prev, ...newItems];
            });

            setNextCursor(parsed.paginationInfo?.nextPageCursor ?? null);
        } finally {
            setLoadingMore(false);
        }
    }


    return (
        <div className="airbnb-container" >
            <h2> Airbnb Search</h2>
            
            {/* Search form */}
            <div className="search-form">
                <label> 
                    Location 
                    <input type="text" value={location}
                        onChange = {(e) => setLocation(e.target.value)}
                        placeholder ="India, Mumbai"
                    />
                </label>
                <br />
                <label>
                    Guests
                    <input type="number" min={1}
                        value = {adults} 
                        onChange={(e) => setAdults(Number(e.target.value))}
                    />
                </label>
                <br />
                <label>
                    Check-in
                    <input type="date" value={checkin}
                    onChange={(e) => setCheckin(e.target.value)}
                    />
                </label>
                <br />
                <label>
                    Check-out
                    <input type="date" value={checkout}
                    onChange={(e) => setCheckout(e.target.value)}
                    />
                </label>
                <br />
                <button onClick={handleSearch}>Search Stays</button>
            </div>

            {/* Loading & error states */}
            {loading && <p>Loading Results...</p>}
            {error && <p style ={{color: "red"}}>{error}</p>}

            {/* External Airbnb link */}
            {searchUrl && (
                <div className="external-link">
                    <a
                    href={searchUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    >
                    🔗 View full results on Airbnb
                    </a>
                </div>
            )}

            {/* Results listing */}
            {results.length > 0 && (
                <div className="results">
                    <h3>Available stays</h3>

                    {results.map((item, idx) => (
                        <ListingCard key={item.id ?? idx} item={item} />

                    ))}
                </div>
            )}

            {/* Load more button for pagination */}
            {nextCursor && (
            <button onClick={handleLoadMore} 
                disabled={!nextCursor || loadingMore}
            >
                {nextCursor ? "Load more" : "No more results"}
            </button>
            )}
        </div>
    );
}