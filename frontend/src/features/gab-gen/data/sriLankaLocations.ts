export interface DistrictOption {
  name: string;
  authorities: {
    type: 'Municipal Council' | 'Urban Council' | 'Pradeshiya Sabha';
    name: string;
  }[];
}

export interface ProvinceOption {
  name: string;
  districts: Record<string, DistrictOption>;
}

export const SRI_LANKA_ADMIN_DATA: Record<string, ProvinceOption> = {
  "Western": {
    name: "Western",
    districts: {
      "Colombo": {
        name: "Colombo",
        authorities: [
          { type: "Municipal Council", name: "Colombo Municipal Council" },
          { type: "Municipal Council", name: "Dehiwala-Mount Lavinia Municipal Council" },
          { type: "Municipal Council", name: "Sri Jayawardenepura Kotte Municipal Council" },
          { type: "Municipal Council", name: "Moratuwa Municipal Council" },
          { type: "Urban Council", name: "Kolonnawa Urban Council" },
          { type: "Urban Council", name: "Seethawaka Urban Council" },
          { type: "Pradeshiya Sabha", name: "Kotikawatta Mulleriyawa Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Homagama Pradeshiya Sabha" }
        ]
      },
      "Gampaha": {
        name: "Gampaha",
        authorities: [
          { type: "Municipal Council", name: "Negombo Municipal Council" },
          { type: "Municipal Council", name: "Gampaha Municipal Council" },
          { type: "Urban Council", name: "Wattala-Mabole Urban Council" },
          { type: "Urban Council", name: "Ja-Ela Urban Council" },
          { type: "Pradeshiya Sabha", name: "Kelaniya Pradeshiya Sabha" }
        ]
      },
      "Kalutara": {
        name: "Kalutara",
        authorities: [
          { type: "Urban Council", name: "Kalutara Urban Council" },
          { type: "Urban Council", name: "Panadura Urban Council" },
          { type: "Urban Council", name: "Horana Urban Council" },
          { type: "Pradeshiya Sabha", name: "Panadura Pradeshiya Sabha" }
        ]
      }
    }
  },
  "Central": {
    name: "Central",
    districts: {
      "Kandy": {
        name: "Kandy",
        authorities: [
          { type: "Municipal Council", name: "Kandy Municipal Council" },
          { type: "Urban Council", name: "Gampola Urban Council" },
          { type: "Pradeshiya Sabha", name: "Harispattuwa Pradeshiya Sabha" }
        ]
      },
      "Matale": {
        name: "Matale",
        authorities: [
          { type: "Municipal Council", name: "Matale Municipal Council" },
          { type: "Pradeshiya Sabha", name: "Matale Pradeshiya Sabha" }
        ]
      },
      "Nuwara Eliya": {
        name: "Nuwara Eliya",
        authorities: [
          { type: "Municipal Council", name: "Nuwara Eliya Municipal Council" },
          { type: "Urban Council", name: "Hatton-Dickoya Urban Council" }
        ]
      }
    }
  },
  "Southern": {
    name: "Southern",
    districts: {
      "Galle": {
        name: "Galle",
        authorities: [
          { type: "Municipal Council", name: "Galle Municipal Council" },
          { type: "Urban Council", name: "Ambalangoda Urban Council" },
          { type: "Pradeshiya Sabha", name: "Bope-Poddala Pradeshiya Sabha" }
        ]
      },
      "Matara": {
        name: "Matara",
        authorities: [
          { type: "Municipal Council", name: "Matara Municipal Council" },
          { type: "Urban Council", name: "Weligama Urban Council" }
        ]
      },
      "Hambantota": {
        name: "Hambantota",
        authorities: [
          { type: "Urban Council", name: "Tangalle Urban Council" },
          { type: "Urban Council", name: "Hambantota Urban Council" }
        ]
      }
    }
  }
};
