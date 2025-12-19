import { useState } from "react";
import { callAirbnbSearch } from "../services/api";
import ListingCard from "../components/ListingCard";


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
    const [location, setLocation] =  useState("");
    const [adults, setAdults] = useState(1);
    const [checkin, setCheckin] = useState("");
    const [checkout, setCheckout] = useState("");

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [results, setResults] = useState<AirbnbListing[]>([]);
    const [searchUrl, setSearchUrl] = useState<string | null>(null);

    const [nextCursor, setNextCursor] = useState<string | null>(null);
    const [loadingMore, setLoadingMore] = useState(false);

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
console.log("Load payload:", payload);
            const data = await callAirbnbSearch(payload);
            const { listings, searchUrl } = parseAirbnbResults(data);
            setResults(listings);
            setSearchUrl(searchUrl)
        }catch (err){
            setError("Something went wrong while fetching results");
        }finally{
            setLoading(false);
        }
    };

    function parseAirbnbResults(raw: any) :
    { listings: AirbnbListing[]; searchUrl: string | null } {
        const textBlock = raw?.result?.content?.[0]?.text;
        if (!textBlock) return { listings: [], searchUrl: null };

        const parsed = JSON.parse(textBlock);
        setNextCursor(parsed.paginationInfo?.nextPageCursor ?? null);
        return {
            listings: (parsed.searchResults || []) as AirbnbListing[],
            searchUrl: parsed.searchUrl || null,
        };
    }
    
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
console.log("Load more payload:", payload);
            const parsed =JSON.parse(textBlock);

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

            {loading && <p>Loading Results...</p>}
            {error && <p style ={{color: "red"}}>{error}</p>}
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
            {results.length > 0 && (
                <div className="results">
                    <h3>Available stays</h3>

                    {results.map((item, idx) => (
                        <ListingCard key={item.id ?? idx} item={item} />

                    ))}
                </div>
            )}
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